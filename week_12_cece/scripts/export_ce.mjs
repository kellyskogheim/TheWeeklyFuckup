import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const [payloadPath, outputPath] = process.argv.slice(2);
if (!payloadPath || !outputPath) {
  throw new Error("Usage: export_ce.mjs PAYLOAD_JSON OUTPUT_XLSX");
}
const payload = JSON.parse(await fs.readFile(payloadPath, "utf8"));
const repoRoot = path.resolve(path.dirname(new URL(import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1")), "..");
const templatePath = path.join(repoRoot, "2023-Actuary-CE-Attestation-spreadsheet-no-identifying-information.xlsx");
const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(templatePath));
const sheet = workbook.worksheets.getItem("CE FORM Appointed Actuary");

sheet.getRange("A2").values = [[
  `To be used for ${payload.year} Continuing Education to meet U.S. Qualification Standards to practice in ${payload.year + 1}`
]];
sheet.getRange("B4").values = [[payload.year]];
sheet.getRange("B5").values = [[
  payload.specific ? "Specific Qualification Standard" : "General Qualification Standard"
]];

const startRow = 14;
const maxRows = 63;
sheet.getRange(`A${startRow}:K${startRow + maxRows - 1}`).clear({ applyTo: "contents" });
const completed = payload.rows.filter((row) => row.status === "completed");
if (completed.length > maxRows) {
  throw new Error(`Template supports ${maxRows} rows; found ${completed.length}.`);
}
if (completed.length) {
  const values = completed.map((row) => [
    new Date(`${row.completed_on}T12:00:00`),
    row.title,
    row.description,
    row.event_name,
    row.minutes,
    null,
    row.activity_kind,
    row.ce_type,
    row.bias_topic ? "Yes" : "No",
    row.specific_education ? "Yes" : "No",
    [
      row.notes,
      row.source_url ? `Source: ${row.source_url}` : "",
      row.needs_review ? "CLASSIFICATION NEEDS REVIEW" : "",
    ].filter(Boolean).join("\n"),
  ]);
  const endRow = startRow + values.length - 1;
  sheet.getRange(`A${startRow}:K${endRow}`).values = values;
  sheet.getRange(`F${startRow}`).formulas = [[`=E${startRow}/50`]];
  sheet.getRange(`F${startRow}:F${endRow}`).fillDown();
  sheet.getRange(`A${startRow}:A${endRow}`).format.numberFormat = "yyyy-mm-dd";
  sheet.getRange(`F${startRow}:F${endRow}`).format.numberFormat = "0.0";
  sheet.getRange(`A${startRow}:K${endRow}`).format.wrapText = true;
}

sheet.getRange("K2").values = [[payload.progress.total]];
sheet.getRange("K3").values = [[payload.progress.organized]];
sheet.getRange("K4").values = [[payload.progress.professionalism]];
sheet.getRange("K5").values = [[payload.progress.bias]];
sheet.getRange("K6").values = [[payload.progress.general_business]];
sheet.getRange("K8").values = [[payload.progress.specific]];
sheet.getRange("K9").values = [[payload.progress.specific_organized]];

const errors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 100 },
  summary: "formula error scan",
});
if (errors.ndjson.includes('"kind":"match"')) {
  console.warn(errors.ndjson);
}
await fs.mkdir(path.dirname(outputPath), { recursive: true });
const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);
