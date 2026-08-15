# -*- coding: utf-8 -*-
import os
import sqlite3
import tempfile
import unittest

from sig_bus.gtfs_edit_core import load_route_stop_times, apply_stop_times


class TestGtfsEditStopTimes(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.gpkg_path = os.path.join(self.temp_dir.name, "test_feed.gpkg")

        conn = sqlite3.connect(self.gpkg_path)
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE routes (
                route_id TEXT,
                route_short_name TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE trips (
                trip_id TEXT,
                route_id TEXT,
                service_id TEXT,
                direction_id INTEGER,
                trip_headsign TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE stop_times (
                trip_id TEXT,
                arrival_time TEXT,
                departure_time TEXT,
                stop_id TEXT,
                stop_sequence INTEGER
            )
        """)

        cursor.execute("""
            CREATE TABLE stops (
                stop_id TEXT,
                stop_name TEXT
            )
        """)
        cursor.execute("INSERT INTO stops VALUES ('S1', 'Parada Central')")
        cursor.execute("INSERT INTO stops VALUES ('S2', 'Estação Norte')")
        cursor.execute("INSERT INTO stops VALUES ('S3', 'Terminal Sul')")

        cursor.execute("INSERT INTO routes VALUES ('R101', '101')")
        cursor.execute("INSERT INTO trips VALUES ('T101_0', 'R101', 'USD', 0, 'Sentido 0')")
        cursor.execute("INSERT INTO trips VALUES ('T101_1', 'R101', 'USD', 1, 'Sentido 1')")
        cursor.execute("INSERT INTO stop_times VALUES ('T101_0', '08:00:00', '08:00:00', 'S1', 1)")
        cursor.execute("INSERT INTO stop_times VALUES ('T101_0', '08:30:00', '08:30:00', 'S2', 2)")
        cursor.execute("INSERT INTO stop_times VALUES ('T101_1', '09:00:00', '09:00:00', 'S2', 1)")
        cursor.execute("INSERT INTO stop_times VALUES ('T101_1', '09:30:00', '09:30:00', 'S1', 2)")

        cursor.execute("INSERT INTO routes VALUES ('R102', '102')")
        cursor.execute("INSERT INTO trips VALUES ('T102_0', 'R102', 'USD', 0, 'Outra Linha')")
        cursor.execute("INSERT INTO stop_times VALUES ('T102_0', '10:00:00', '10:00:00', 'S3', 1)")

        conn.commit()
        conn.close()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_load_route_stop_times_filtra_linha_e_organiza_por_sentido(self):
        res = load_route_stop_times(self.gpkg_path, "101")
        self.assertIn(0, res)
        self.assertIn(1, res)
        self.assertEqual(res[0]["trip_headsign"], "Sentido 0")
        self.assertEqual(res[1]["trip_headsign"], "Sentido 1")
        self.assertEqual(len(res[0]["stop_times"]), 2)
        self.assertEqual(len(res[1]["stop_times"]), 2)

        trip_ids = [st["trip_id"] for dir_data in res.values() for st in dir_data["stop_times"]]
        self.assertIn("T101_0", trip_ids)
        self.assertIn("T101_1", trip_ids)
        self.assertNotIn("T102_0", trip_ids)

    def test_load_route_stop_times_devolve_nome_da_parada(self):
        res = load_route_stop_times(self.gpkg_path, "101")
        st_0 = res[0]["stop_times"]
        self.assertEqual(st_0[0]["stop_name"], "Parada Central")
        self.assertEqual(st_0[1]["stop_name"], "Estação Norte")

    def test_load_route_stop_times_sem_nome_preenchido_cai_no_stop_id(self):
        conn = sqlite3.connect(self.gpkg_path)
        conn.execute("UPDATE stops SET stop_name = NULL")
        conn.commit()
        conn.close()

        res = load_route_stop_times(self.gpkg_path, "101")
        st_0 = res[0]["stop_times"]
        self.assertIsNone(st_0[0]["stop_name"])

        from sig_bus.schedule_table_core import build_schedule_table
        table = build_schedule_table(st_0)
        self.assertEqual(table.stops[0]["stop_name"], "S1")

    def test_load_route_stop_times_sem_tabela_stops_nao_quebra(self):
        conn = sqlite3.connect(self.gpkg_path)
        conn.execute("DROP TABLE stops")
        conn.commit()
        conn.close()

        res = load_route_stop_times(self.gpkg_path, "101")
        self.assertEqual(len(res[0]["stop_times"]), 2)
        self.assertNotIn("stop_name", res[0]["stop_times"][0])

    def test_load_route_stop_times_service_id(self):
        res = load_route_stop_times(self.gpkg_path, "101", service_id="INEXISTENTE")
        self.assertEqual(res, {})

    def test_load_route_stop_times_ambas_direcoes_com_headsigns_e_tabela(self):
        from sig_bus.schedule_table_core import build_schedule_table
        res = load_route_stop_times(self.gpkg_path, "101")
        self.assertEqual(set(res.keys()), {0, 1})
        self.assertEqual(res[0]["trip_headsign"], "Sentido 0")
        self.assertEqual(res[1]["trip_headsign"], "Sentido 1")

        table_0 = build_schedule_table(res[0]["stop_times"], route_short_name="101", direction_id=0)
        table_1 = build_schedule_table(res[1]["stop_times"], route_short_name="101", direction_id=1)

        headers_0, rows_0 = table_0.to_grid()
        headers_1, rows_1 = table_1.to_grid()

        # O cabeçalho é rótulo legível; o trip_id vem de column_trip_ids().
        self.assertEqual(headers_0, ["Parada", "V1\n08:00"])
        self.assertEqual(table_0.column_trip_ids(), ["T101_0"])
        self.assertEqual(table_1.column_trip_ids(), ["T101_1"])
        self.assertEqual(len(rows_0), 2)
        self.assertEqual(len(rows_1), 2)

    def test_apply_stop_times_altera_apenas_horarios_especificados(self):
        st_mod = [
            {"trip_id": "T101_0", "stop_sequence": 1, "arrival_time": "08:05:00", "departure_time": "08:06:00"}
        ]
        afetados = apply_stop_times(self.gpkg_path, st_mod)
        self.assertEqual(afetados, 1)

        conn = sqlite3.connect(self.gpkg_path)
        cursor = conn.cursor()
        cursor.execute("SELECT arrival_time, departure_time FROM stop_times WHERE trip_id='T101_0' AND stop_sequence=1")
        row = cursor.fetchone()
        conn.close()

        self.assertEqual(row, ("08:05:00", "08:06:00"))

    def test_apply_stop_times_trip_id_inexistente(self):
        st_invalido = [
            {"trip_id": "T99999", "stop_sequence": 1, "arrival_time": "12:00:00", "departure_time": "12:00:00"}
        ]
        afetados = apply_stop_times(self.gpkg_path, st_invalido)
        self.assertEqual(afetados, 0)

    def test_open_schedule_edit_dialog_aplicar_ao_feed(self):
        """Passo 182: só a célula alterada vira UPDATE, e ela vai para o feed."""
        from qgis.PyQt.QtWidgets import (QApplication, QWidget, QPushButton,
                                         QTableWidget, QDialog)
        from sig_bus.SigBus_dialog import SigBusDialog

        self._app = QApplication.instance() or QApplication([])

        dirs_data = load_route_stop_times(self.gpkg_path, "101")

        class _DonoFalso(QWidget):
            """O mínimo que _open_schedule_edit_dialog usa do diálogo real."""
            def __init__(self, gpkg):
                super().__init__()
                self._working_copy = type("WC", (), {"edit_path": gpkg})()
                self.status_atualizado = False

            def _refresh_edit_status(self):
                self.status_atualizado = True

        dono = _DonoFalso(self.gpkg_path)
        abrir = SigBusDialog._open_schedule_edit_dialog.__get__(dono, SigBusDialog)

        editado = {}

        def mock_exec(d_self):
            d_self.show()
            btn_apply = next(b for b in d_self.findChildren(QPushButton)
                             if b.text() == "Aplicar ao feed")
            # O trip_id não está mais no rótulo do cabeçalho: vem do tooltip
            # — é por ele que a aba do sentido 0 é localizada.
            tabela = next(t for t in d_self.findChildren(QTableWidget)
                          if t.horizontalHeaderItem(1)
                          and t.horizontalHeaderItem(1).toolTip() == "T101_0")
            editado["trip_id"] = tabela.horizontalHeaderItem(1).toolTip()
            editado["antes"] = tabela.item(1, 1).text()
            tabela.item(0, 1).setText("08:12:00")
            btn_apply.click()
            return 1

        old_exec = QDialog.exec
        QDialog.exec = mock_exec
        try:
            abrir("101", dirs_data)
        finally:
            QDialog.exec = old_exec

        self.assertTrue(dono.status_atualizado)

        conn = sqlite3.connect(self.gpkg_path)
        cursor = conn.cursor()
        cursor.execute("SELECT arrival_time, departure_time FROM stop_times "
                       "WHERE trip_id=? AND stop_sequence=1", (editado["trip_id"],))
        self.assertEqual(cursor.fetchone(), ("08:12:00", "08:12:00"))
        # Decisão 112: a célula editada desloca a VIAGEM INTEIRA — os 12 min
        # da primeira parada valem também para a segunda, que era 08:30.
        self.assertEqual(editado["antes"], "08:30:00")
        cursor.execute("SELECT departure_time FROM stop_times "
                       "WHERE trip_id=? AND stop_sequence=2", (editado["trip_id"],))
        self.assertEqual(cursor.fetchone()[0], "08:42:00")
        # O outro sentido da mesma linha não foi tocado.
        cursor.execute("SELECT departure_time FROM stop_times "
                       "WHERE trip_id='T101_1' AND stop_sequence=1")
        self.assertEqual(cursor.fetchone()[0], "09:00:00")
        # A outra linha do feed continua intacta.
        cursor.execute("SELECT arrival_time FROM stop_times WHERE trip_id='T102_0'")
        self.assertEqual(cursor.fetchone()[0], "10:00:00")
        conn.close()

    def test_janela_de_horarios_cabe_na_tela_e_lembra_a_geometria(self):
        """Passos 213/215: a janela nasce clampada à área útil e grava a
        geometria no QSettings ao terminar (decisões 148 e 152)."""
        from qgis.PyQt.QtCore import QSettings
        from qgis.PyQt.QtWidgets import QApplication, QDialog, QWidget
        from sig_bus.SigBus_dialog import SigBusDialog, _SCHEDULE_DIALOG_GEOM_KEY

        self._app = QApplication.instance() or QApplication([])
        dirs_data = load_route_stop_times(self.gpkg_path, "101")

        class _DonoFalso(QWidget):
            def __init__(self, gpkg):
                super().__init__()
                self._working_copy = type("WC", (), {"edit_path": gpkg})()

            def _refresh_edit_status(self):
                pass

        dono = _DonoFalso(self.gpkg_path)
        abrir = SigBusDialog._open_schedule_edit_dialog.__get__(dono, SigBusDialog)

        settings = QSettings()
        settings.remove(_SCHEDULE_DIALOG_GEOM_KEY)

        aberto = {}

        def mock_exec(d_self):
            aberto["dialog"] = d_self
            d_self.finished.emit(0)       # o usuário fecha a janela
            return 0

        old_exec = QDialog.exec
        QDialog.exec = mock_exec
        try:
            abrir("101", dirs_data)
        finally:
            QDialog.exec = old_exec

        dialog = aberto.get("dialog")
        self.assertIsNotNone(dialog)

        # Nunca maior que a tela em que abriu (o padrão pedido é 1180x620).
        area = QApplication.primaryScreen().availableGeometry()
        self.assertLessEqual(dialog.width(), area.width())
        self.assertLessEqual(dialog.height(), area.height())
        self.assertGreater(dialog.width(), 0)

        # A geometria foi para o QSettings — e só para lá.
        try:
            self.assertIsNotNone(settings.value(_SCHEDULE_DIALOG_GEOM_KEY))
        finally:
            settings.remove(_SCHEDULE_DIALOG_GEOM_KEY)

    def test_gtfs_edit_stop_times_validacao_e_exportacao_ciclo_completo(self):
        from osgeo import ogr
        from sig_bus.gtfs_validator import GtfsValidator
        from sig_bus.gtfs_export import GtfsExporter

        complete_gpkg = os.path.join(self.temp_dir.name, "complete_feed.gpkg")
        driver = ogr.GetDriverByName("GPKG")
        ds = driver.CreateDataSource(complete_gpkg)
        lyr = ds.CreateLayer("stops", geom_type=ogr.wkbPoint)
        field_defn = ogr.FieldDefn("stop_id", ogr.OFTString)
        lyr.CreateField(field_defn)
        field_name = ogr.FieldDefn("stop_name", ogr.OFTString)
        lyr.CreateField(field_name)

        feat1 = ogr.Feature(lyr.GetLayerDefn())
        feat1.SetField("stop_id", "S1")
        feat1.SetField("stop_name", "Parada 1")
        pt1 = ogr.Geometry(ogr.wkbPoint)
        pt1.AddPoint(-43.9, -19.9)
        feat1.SetGeometry(pt1)
        lyr.CreateFeature(feat1)

        feat2 = ogr.Feature(lyr.GetLayerDefn())
        feat2.SetField("stop_id", "S2")
        feat2.SetField("stop_name", "Parada 2")
        pt2 = ogr.Geometry(ogr.wkbPoint)
        pt2.AddPoint(-43.91, -19.91)
        feat2.SetGeometry(pt2)
        lyr.CreateFeature(feat2)
        ds = None

        conn = sqlite3.connect(complete_gpkg)
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE agency (agency_id TEXT, agency_name TEXT, agency_url TEXT, agency_timezone TEXT)")
        cursor.execute("INSERT INTO agency VALUES ('A1', 'Agencia', 'http://example.com', 'America/Sao_Paulo')")
        cursor.execute("CREATE TABLE routes (route_id TEXT, route_short_name TEXT, agency_id TEXT)")
        cursor.execute("INSERT INTO routes VALUES ('R101', '101', 'A1')")
        cursor.execute("CREATE TABLE trips (trip_id TEXT, route_id TEXT, service_id TEXT, direction_id INTEGER, trip_headsign TEXT, shape_id TEXT)")
        cursor.execute("INSERT INTO trips VALUES ('T101_0', 'R101', 'USD', 0, 'Sentido 0', NULL)")
        cursor.execute("CREATE TABLE stop_times (trip_id TEXT, arrival_time TEXT, departure_time TEXT, stop_id TEXT, stop_sequence INTEGER)")
        cursor.execute("INSERT INTO stop_times VALUES ('T101_0', '08:00:00', '08:00:00', 'S1', 1)")
        cursor.execute("INSERT INTO stop_times VALUES ('T101_0', '08:30:00', '08:30:00', 'S2', 2)")
        cursor.execute("CREATE TABLE calendar (service_id TEXT, monday INT, tuesday INT, wednesday INT, thursday INT, friday INT, saturday INT, sunday INT, start_date TEXT, end_date TEXT)")
        cursor.execute("INSERT INTO calendar VALUES ('USD', 1, 1, 1, 1, 1, 0, 0, '20260101', '20261231')")
        conn.commit()
        conn.close()

        # 1. Modifica horários via apply_stop_times
        st_mod = [
            {"trip_id": "T101_0", "stop_sequence": 1, "arrival_time": "08:15:00", "departure_time": "08:15:00"}
        ]
        apply_stop_times(complete_gpkg, st_mod)

        # 2. Valida o GTFS editado
        validator = GtfsValidator(complete_gpkg)
        errors, warnings = validator.validate()
        self.assertEqual(errors, [])

        # 2.1 Horário fora de ordem dentro da mesma viagem é erro (passo 183)
        conn = sqlite3.connect(complete_gpkg)
        conn.execute("UPDATE stop_times SET arrival_time='07:00:00', departure_time='07:00:00' "
                     "WHERE trip_id='T101_0' AND stop_sequence=2")
        conn.commit()
        conn.close()

        erros_ordem, _ = GtfsValidator(complete_gpkg).validate()
        self.assertTrue(any("fora de ordem" in e for e in erros_ordem), erros_ordem)

        conn = sqlite3.connect(complete_gpkg)
        conn.execute("UPDATE stop_times SET arrival_time='08:30:00', departure_time='08:30:00' "
                     "WHERE trip_id='T101_0' AND stop_sequence=2")
        conn.commit()
        conn.close()

        # 3. Exporta para .zip
        out_zip = os.path.join(self.temp_dir.name, "gtfs_exportado.zip")
        exporter = GtfsExporter(complete_gpkg, out_zip)
        res = exporter.run()
        self.assertTrue(res)
        self.assertTrue(os.path.exists(out_zip))

        # 4. Confere o arquivo .zip gerado
        import zipfile
        with zipfile.ZipFile(out_zip, 'r') as zf:
            namelist = zf.namelist()
            self.assertIn("stop_times.txt", namelist)
            self.assertIn("stops.txt", namelist)
            content = zf.read("stop_times.txt").decode("utf-8")
            self.assertIn("08:15:00", content)

    def test_schedule_grid_widget_cabecalho_legivel(self):
        """Passo 197 / Decisão 135: verifica se o cabeçalho da matriz de horários possui tooltips e formatação legível."""
        from qgis.PyQt.QtWidgets import QApplication
        from sig_bus.schedule_grid_widget import ScheduleGridWidget

        self._app = QApplication.instance() or QApplication([])

        stop_times = [
            {"trip_id": "T101_0", "stop_id": "S1", "stop_sequence": 1, "departure_time": "08:00:00"},
            {"trip_id": "T101_0", "stop_id": "S2", "stop_sequence": 2, "departure_time": "08:15:00"},
        ]
        grid = ScheduleGridWidget(stop_times, route_short_name="101", direction_id="0")

        # Cabeçalho legível: ordinal + primeira saída (decisão 135)
        self.assertEqual(grid.columnCount(), 2)
        self.assertEqual(grid.horizontalHeaderItem(0).text(), "Parada")
        self.assertEqual(grid.horizontalHeaderItem(1).text(), "V1\n08:00")

        # O trip_id sai do rótulo e vira tooltip, para casar com o feed.
        self.assertEqual(grid.horizontalHeaderItem(1).toolTip(), "T101_0")
        # A primeira coluna traz o stop_id no tooltip (decisão 136).
        self.assertEqual(grid.item(0, 0).toolTip(), "S1")

    def test_schedule_grid_widget_nao_le_trip_id_do_cabecalho(self):
        """Passo 198: ScheduleGridWidget deixa de ler o trip_id do cabeçalho."""
        from qgis.PyQt.QtWidgets import QApplication, QTableWidgetItem
        from sig_bus.schedule_grid_widget import ScheduleGridWidget

        self._app = QApplication.instance() or QApplication([])

        stop_times = [
            {"trip_id": "T101_0", "stop_id": "S1", "stop_sequence": 1, "departure_time": "08:00:00"},
            {"trip_id": "T101_0", "stop_id": "S2", "stop_sequence": 2, "departure_time": "08:15:00"},
        ]
        grid = ScheduleGridWidget(stop_times, route_short_name="101", direction_id="0")

        # Altera o texto do cabeçalho da coluna 1 para um rótulo customizado
        grid.headers[1] = "Rotulo_Modificado"
        grid.setHorizontalHeaderItem(1, QTableWidgetItem("Rotulo_Modificado"))

        # Modifica célula (linha 0, coluna 1)
        grid.item(0, 1).setText("08:05:00")

        alterados, grade_val, ilegiveis = grid.collect_changes()

        # O trip_id retornado em alterados deve ser o original T101_0 do table_obj.trips, não o do cabeçalho
        self.assertEqual(len(alterados), 1)
        self.assertEqual(alterados[0]["trip_id"], "T101_0")
        self.assertEqual(alterados[0]["departure_time"], "08:05:00")


if __name__ == "__main__":
    unittest.main()
