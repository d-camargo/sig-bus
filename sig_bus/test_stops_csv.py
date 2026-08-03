"""Testes para sig_bus/stops_csv.py."""

import csv
import io

from sig_bus.stops_csv import (
    CSV_DELIMITER,
    CSV_HEADER,
    write_template,
    parse_stops_csv,
)


def test_write_template_e_parse_ida_e_volta(tmp_path):
    caminho = tmp_path / "modelo.csv"
    write_template(str(caminho))

    # BOM UTF-8 presente
    with open(caminho, "rb") as f:
        assert f.read(3) == b"\xef\xbb\xbf"

    linhas_ok, erros = parse_stops_csv(str(caminho))
    assert erros == []
    assert len(linhas_ok) == 2

    urbana, rural = linhas_ok
    assert urbana["sequencia"] == 1
    assert urbana["endereco"] == "Rua Giuseppe Fórmolo, 210 - Centro"
    assert urbana["lat"] is None and urbana["lon"] is None

    assert rural["sequencia"] == 2
    assert rural["endereco"] == ""
    assert rural["lat"] == -29.1634
    assert rural["lon"] == -51.1794


def test_parse_coluna_opcional_ausente(tmp_path):
    # Cabeçalho sem a coluna "observacao" (opcional)
    caminho = tmp_path / "sem_observacao.csv"
    with open(caminho, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f, delimiter=CSV_DELIMITER)
        writer.writerow(["sequencia", "nome_parada", "logradouro", "numero",
                          "bairro", "latitude", "longitude"])
        writer.writerow(["1", "Praça Central", "Rua A", "10", "Centro", "", ""])

    linhas_ok, erros = parse_stops_csv(str(caminho))
    assert erros == []
    assert len(linhas_ok) == 1
    assert linhas_ok[0]["observacao"] == ""
    assert linhas_ok[0]["endereco"] == "Rua A, 10 - Centro"


def test_parse_cabecalho_com_acento_e_maiuscula(tmp_path):
    caminho = tmp_path / "acentuado.csv"
    with open(caminho, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f, delimiter=CSV_DELIMITER)
        writer.writerow(["Sequência", "Nome_Parada", "Logradouro", "Número",
                          "Bairro", "Latitude", "Longitude", "Observação"])
        writer.writerow(["1", "Praça Central", "Rua A", "10", "Centro",
                          "", "", ""])

    linhas_ok, erros = parse_stops_csv(str(caminho))
    assert erros == []
    assert len(linhas_ok) == 1


def test_parse_linha_sem_endereco_e_sem_coordenadas_vira_erro(tmp_path):
    caminho = tmp_path / "invalida.csv"
    with open(caminho, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f, delimiter=CSV_DELIMITER)
        writer.writerow(CSV_HEADER)
        writer.writerow(["1", "Parada sem nada", "", "", "", "", "", ""])

    linhas_ok, erros = parse_stops_csv(str(caminho))
    assert linhas_ok == []
    assert len(erros) == 1
    assert "Linha 2" in erros[0]


def test_parse_linha_so_com_latlon_e_valida(tmp_path):
    caminho = tmp_path / "rural.csv"
    with open(caminho, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f, delimiter=CSV_DELIMITER)
        writer.writerow(CSV_HEADER)
        writer.writerow(["1", "Trevo", "", "", "", "-29,1634", "-51,1794", ""])

    linhas_ok, erros = parse_stops_csv(str(caminho))
    assert erros == []
    assert len(linhas_ok) == 1
    assert linhas_ok[0]["lat"] == -29.1634
    assert linhas_ok[0]["lon"] == -51.1794


def test_parse_delimitador_errado_produz_erro_legivel(tmp_path):
    caminho = tmp_path / "delimitador_errado.csv"
    # Escrito com vírgula em vez de ';'
    with open(caminho, "w", encoding="utf-8-sig", newline="") as f:
        f.write(",".join(CSV_HEADER) + "\n")
        f.write("1,Praça Central,Rua A,10,Centro,,,\n")

    linhas_ok, erros = parse_stops_csv(str(caminho))
    assert linhas_ok == []
    assert len(erros) == 1
    assert "delimitador" in erros[0].lower()


def test_import_stops_csv_dialog_logic(tmp_path, monkeypatch):
    """Testa o fluxo do passo 85: importar CSV preenche as linhas da página Paradas."""
    import os

    import pytest
    # Só roda com QGIS/Qt reais: os mocks do conftest não montam widgets.
    if os.environ.get('FORCE_MOCK_QGIS'):
        pytest.skip("exige QGIS real (rodando com os mocks do conftest)")
    pytest.importorskip("qgis.gui", reason="exige QGIS real")
    from qgis.PyQt.QtWidgets import QApplication, QFileDialog, QMessageBox
    from sig_bus.SigBus_dialog import SigBusDialog

    app = QApplication.instance() or QApplication([])

    caminho = tmp_path / "3_paradas.csv"
    with open(caminho, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f, delimiter=CSV_DELIMITER)
        writer.writerow(CSV_HEADER)
        writer.writerow(["1", "Parada 1", "Rua Um", "100", "Bairro A", "", "", ""])
        writer.writerow(["2", "Parada Rural", "", "", "", "-29.123", "-51.456", ""])
        writer.writerow(["3", "Parada 3", "Rua Três", "300", "Bairro B", "", "", ""])

    dialog = SigBusDialog(None)
    assert hasattr(dialog, "button_download_csv_template")
    assert hasattr(dialog, "button_import_csv")
    assert dialog.button_download_csv_template.text() == "Baixar modelo CSV"
    assert dialog.button_import_csv.text() == "Importar CSV"

    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args, **kwargs: (str(caminho), "CSV"))
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: None)
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Yes)

    dialog._import_stops_csv()

    assert len(dialog.stop_rows) == 3
    row1, row2, row3 = dialog.stop_rows

    assert row1["input_address"].text() == "Rua Um, 100 - Bairro A"
    assert row1["lat"] is None and row1["lon"] is None

    assert row2["input_address"].text() == "Parada Rural"
    assert row2["lat"] == -29.123 and row2["lon"] == -51.456
    assert row2["label_status"].text() == "✓ localizado"

    assert row3["input_address"].text() == "Rua Três, 300 - Bairro B"
    assert row3["lat"] is None and row3["lon"] is None

    salvar_caminho = tmp_path / "salvo_modelo.csv"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args, **kwargs: (str(salvar_caminho), "CSV"))
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)
    dialog._download_csv_template()
    assert salvar_caminho.exists()


