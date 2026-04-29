import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';
import ts from 'typescript';

const __dirname = dirname(fileURLToPath(import.meta.url));
const require = createRequire(import.meta.url);
const sourcePath = resolve(__dirname, '../src/utils/pdfHighlights.ts');
const source = readFileSync(sourcePath, 'utf8');
const module = { exports: {} };
const compiled = ts.transpileModule(source, {
  compilerOptions: {
    module: ts.ModuleKind.CommonJS,
    target: ts.ScriptTarget.ES2022,
  },
});

vm.runInNewContext(compiled.outputText, {
  module,
  exports: module.exports,
  require,
}, { filename: sourcePath });

const { buildSourceHighlights } = module.exports;

const question = {
  source_bbox: [1, 2, 3, 4],
  source_page_start: 9,
  pdf_source: {
    source_bbox: [10, 20, 70, 90],
    source_page_start: 2,
  },
  visual_refs: [
    { id: 'p1-img2', page: 1, bbox: [100, 110, 300, 330] },
  ],
  images: [
    { ref: 'p1-img2', bbox: [120, 140, 340, 360] },
  ],
};

const plain = (value) => JSON.parse(JSON.stringify(value));

assert.deepEqual(plain(buildSourceHighlights(question)), [
  {
    page: 2,
    x: 10,
    y: 20,
    width: 60,
    height: 70,
    label: '题目区域',
  },
]);

assert.deepEqual(plain(buildSourceHighlights({
  visual_refs: [{ id: 'p1-img2', page: 1, bbox: [100, 110, 300, 330] }],
  images: [{ ref: 'p1-img2', bbox: [120, 140, 340, 360] }],
})), []);
