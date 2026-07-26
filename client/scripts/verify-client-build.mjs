import { stat } from 'node:fs/promises';
import { fileURLToPath, pathToFileURL } from 'node:url';
import path from 'node:path';

export const EXPECTED_CLIENT_OUTPUTS = [
  'main/css/main.css',
  'stats/css/stats.css',
  'main/js/enums.js',
  'main/js/main.js',
  'main/js/main.js.map',
];

const CLIENT_ROOT = fileURLToPath(new URL('../', import.meta.url));

export async function findInvalidClientOutputs(root = CLIENT_ROOT) {
  const invalid = [];
  for (const output of EXPECTED_CLIENT_OUTPUTS) {
    try {
      const metadata = await stat(path.join(root, output));
      if (!metadata.isFile() || metadata.size === 0) {
        invalid.push(output);
      }
    } catch {
      invalid.push(output);
    }
  }
  return invalid;
}

async function main() {
  const invalid = await findInvalidClientOutputs();
  for (const output of invalid) {
    console.error(`missing or empty client build output: ${output}`);
  }
  if (invalid.length > 0) {
    process.exitCode = 1;
  }
}

if (
  process.argv[1] &&
  import.meta.url === pathToFileURL(process.argv[1]).href
) {
  await main();
}
