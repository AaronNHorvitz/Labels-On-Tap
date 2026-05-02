"""Tests for the local public COLA ETL parser/import helpers."""

from __future__ import annotations

from pathlib import Path

from scripts.cola_etl.csv_import import read_registry_csv
from scripts.cola_etl.parser import parse_public_cola_form


SAMPLE_FORM_HTML = """
<html>
  <body>
    <form>
      <div class="label">TTB ID</div>
      <div class="data">25337001000464</div>

      <table>
        <tr>
          <td>
            <div class="boldlabel">2. PLANT REGISTRY/BASIC PERMIT/BREWER'S NO. <i>(Required)</i></div>
            <div class="data">DSP-KY-20176</div>
          </td>
          <td>
            <div class="label">3. SOURCE OF PRODUCT <i>(Required)</i></div>
            <input type="checkbox" checked alt="Source of Product: Domestic">
          </td>
        </tr>
        <tr>
          <td>
            <div class="label">4. SERIAL NUMBER <i>(Required)</i></div>
            <div class="data">250018</div>
          </td>
          <td>
            <div class="label">5. TYPE OF PRODUCT <i>(Required)</i></div>
            <input type="checkbox" checked alt="Type of Product: Distilled Spirits">
          </td>
        </tr>
        <tr>
          <td>
            <div class="boldlabel">6. BRAND NAME <i>(Required)</i></div>
            <div class="data">KENTUCKY RAMBLER</div>
          </td>
          <td>
            <div class="boldlabel">7. FANCIFUL NAME <i>(If any)</i></div>
            <div class="data">CASK STRENGTH</div>
          </td>
        </tr>
        <tr>
          <td>
            <div class="label">8. NAME AND ADDRESS OF APPLICANT</div>
            <div class="data">KENTUCKY RAMBLER DISTILLING<br>LOUISVILLE KY 40202</div>
          </td>
        </tr>
        <tr>
          <td>
            <div class="label">11. FORMULA</div>
            <div class="data">FORM-123</div>
          </td>
          <td>
            <div class="boldlabel">12. NET CONTENTS</div>
            <div class="data">750 mL</div>
          </td>
          <td>
            <div class="label">13. ALCOHOL CONTENT</div>
            <div class="data">55.5</div>
          </td>
        </tr>
        <tr>
          <td>
            <div class="label">18. TYPE OF APPLICATION</div>
            <input type="checkbox" checked alt="Type of Application">
            CERTIFICATE OF LABEL APPROVAL
          </td>
        </tr>
      </table>

      <div class="boldlabel">STATUS</div>
      <div class="data">THE STATUS IS APPROVED.</div>
      <div class="boldlabel">CLASS/TYPE DESCRIPTION</div>
      <div class="data">STRAIGHT BOURBON WHISKY</div>

      <p class="data">AFFIX COMPLETE SET OF LABELS BELOW</p>
      <p class="data">Image Type:</p>
      Brand (front)
      <br>
      Actual Dimensions: 3.5 inches W X 4 inches H
      <img src="/colasonline/publicViewAttachment.do?filename=front label.jpg&filetype=l"
           width="350" height="400" alt="Label Image: Brand (front)">

      <p class="data">Image Type:</p>
      Back
      <br>
      Actual Dimensions: 3 inches W X 3 inches H
      <img src="/colasonline/publicViewAttachment.do?filename=back label.jpg&filetype=l"
           width="300" height="300" alt="Label Image: Back">

      <img src="/colasonline/publicViewSignature.do?ttbid=25337001000464" alt="signature">
    </form>
  </body>
</html>
"""


def test_parse_public_cola_form_extracts_fields_and_label_attachments() -> None:
    parsed = parse_public_cola_form(
        SAMPLE_FORM_HTML,
        source_url=(
            "https://ttbonline.gov/colasonline/viewColaDetails.do"
            "?action=publicFormDisplay&ttbid=25337001000464"
        ),
    )

    assert parsed["ttb_id"] == "25337001000464"
    assert parsed["form_fields"]["brand_name"] == "KENTUCKY RAMBLER"
    assert parsed["form_fields"]["fanciful_name"] == "CASK STRENGTH"
    assert parsed["form_fields"]["status"] == "approved"
    assert parsed["application"]["product_type"] == "distilled_spirits"
    assert parsed["application"]["class_type"] == "STRAIGHT BOURBON WHISKY"
    assert parsed["application"]["alcohol_content"] == "55.5"
    assert parsed["application"]["net_contents"] == "750 mL"
    assert parsed["application"]["imported"] is False

    assert len(parsed["attachments"]) == 2
    assert parsed["attachments"][0]["filename"] == "front label.jpg"
    assert parsed["attachments"][0]["image_type"] == "Brand (front)"
    assert parsed["attachments"][0]["width_inches"] == 3.5
    assert parsed["attachments"][0]["height_inches"] == 4.0
    assert parsed["attachments"][0]["source_url"].startswith(
        "https://ttbonline.gov/colasonline/publicViewAttachment.do"
    )
    assert parsed["attachments"][1]["filename"] == "back label.jpg"
    assert parsed["attachments"][1]["image_type"] == "Back"


def test_read_registry_csv_normalizes_ttb_export_headers(tmp_path: Path) -> None:
    csv_path = tmp_path / "registry.csv"
    csv_path.write_text(
        "\ufeffTTB ID,Permit No.,Serial Number,Completed Date,Fanciful Name,"
        "Brand Name,Origin,Origin Desc,Class/Type,Class/Type Desc\n"
        "25337001000464,DSP-KY-20176,250018,04/30/2026,CASK STRENGTH,"
        "KENTUCKY RAMBLER,22,KENTUCKY,101,STRAIGHT BOURBON WHISKY\n",
        encoding="utf-8",
    )

    rows = read_registry_csv(csv_path)

    assert rows == [
        {
            "ttb_id": "25337001000464",
            "permit_no": "DSP-KY-20176",
            "serial_number": "250018",
            "completed_date": "04/30/2026",
            "fanciful_name": "CASK STRENGTH",
            "brand_name": "KENTUCKY RAMBLER",
            "origin": "22",
            "origin_desc": "KENTUCKY",
            "class_type": "101",
            "class_type_desc": "STRAIGHT BOURBON WHISKY",
        }
    ]
