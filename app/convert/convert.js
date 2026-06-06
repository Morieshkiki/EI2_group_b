// convert.js
// FS - This was done to convert the sample IFC file to XKT format for performance
// FS - Copilot and Autocomplete were used to generate this file, but it was also based on the example code from the xeokit-convert package documentation:
import { convert2xkt } from '@xeokit/xeokit-convert';
import path from 'path';

const [,, sourcePath, outputPath] = process.argv;

if (!sourcePath || !outputPath) {
  console.error("Usage: node convert.js <input.ifc> <output.xkt>");
  process.exit(1);
}

convert2xkt({
  source: sourcePath,
  output: outputPath,
  log: msg => console.log(`[convert2xkt] ${msg}`)
}).then(() => {
  console.log("Conversion complete.");
}).catch(err => {
  console.error("Conversion failed:", err);
  process.exit(1);
});
