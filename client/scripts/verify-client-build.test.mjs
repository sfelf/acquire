import assert from 'node:assert/strict';
import { mkdir, mkdtemp, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import test from 'node:test';

import { EXPECTED_CLIENT_OUTPUTS, findInvalidClientOutputs } from './verify-client-build.mjs';

test('client output verification reports every missing output', async (t) => {
  const root = await mkdtemp(path.join(tmpdir(), 'acquire-client-build-'));
  t.after(() => rm(root, { recursive: true, force: true }));

  for (const output of EXPECTED_CLIENT_OUTPUTS) {
    const outputPath = path.join(root, output);
    await mkdir(path.dirname(outputPath), { recursive: true });
    await writeFile(outputPath, 'generated');
  }
  assert.deepEqual(await findInvalidClientOutputs(root), []);

  for (const output of EXPECTED_CLIENT_OUTPUTS) {
    const outputPath = path.join(root, output);
    await rm(outputPath);
    assert.deepEqual(await findInvalidClientOutputs(root), [output]);
    await writeFile(outputPath, 'generated');
  }
});

test('client output verification rejects empty output files', async (t) => {
  const root = await mkdtemp(path.join(tmpdir(), 'acquire-client-build-'));
  t.after(() => rm(root, { recursive: true, force: true }));

  for (const output of EXPECTED_CLIENT_OUTPUTS) {
    const outputPath = path.join(root, output);
    await mkdir(path.dirname(outputPath), { recursive: true });
    await writeFile(outputPath, 'generated');
  }
  await writeFile(path.join(root, EXPECTED_CLIENT_OUTPUTS[0]), '');

  assert.deepEqual(await findInvalidClientOutputs(root), [EXPECTED_CLIENT_OUTPUTS[0]]);
});
