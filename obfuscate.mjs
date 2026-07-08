/**
 * obfuscate.mjs  –  Run: node obfuscate.mjs
 * Obfuscates JS inside index.html and student.html in-place.
 */
import fs from "fs";
import JavaScriptObfuscator from "javascript-obfuscator";
import { minify as minifyHtml } from "html-minifier-terser";

const FILES = ["index.html", "student.html"];

const OBF = {
  compact: true,
  controlFlowFlattening: true,
  controlFlowFlatteningThreshold: 0.75,
  deadCodeInjection: true,
  deadCodeInjectionThreshold: 0.4,
  disableConsoleOutput: true,
  identifierNamesGenerator: "hexadecimal",
  numbersToExpressions: true,
  renameGlobals: false,
  selfDefending: true,
  simplify: true,
  splitStrings: true,
  splitStringsChunkLength: 10,
  stringArray: true,
  stringArrayCallsTransform: true,
  stringArrayCallsTransformThreshold: 0.75,
  stringArrayEncoding: ["base64"],
  stringArrayIndexShift: true,
  stringArrayRotate: true,
  stringArrayShuffle: true,
  stringArrayWrappersCount: 2,
  stringArrayWrappersParametersMaxCount: 4,
  stringArrayWrappersChained: true,
  stringArrayWrappersType: "function",
  stringArrayThreshold: 0.75,
  transformObjectKeys: false,
  unicodeEscapeSequence: false,
};

const HTML_OPTS = {
  collapseWhitespace: true,
  removeComments: true,
  removeRedundantAttributes: true,
  removeScriptTypeAttributes: true,
  removeStyleLinkTypeAttributes: true,
  minifyCSS: true,
  minifyJS: false,
  useShortDoctype: true,
};

async function processFile(file) {
  console.log("Processing " + file + " ...");
  let html = fs.readFileSync(file, "utf8");

  const scriptRx = /<script(?![^>]*src=)([^>]*)>([\s\S]*?)<\/script>/gi;
  let n = 0;
  html = html.replace(scriptRx, (match, attrs, code) => {
    const t = code.trim();
    if (!t || t.length < 50) return match;
    try {
      const obf = JavaScriptObfuscator.obfuscate(t, OBF).getObfuscatedCode();
      n++;
      return "<script" + attrs + ">" + obf + "</script>";
    } catch (e) {
      console.warn("  skip block: " + e.message);
      return match;
    }
  });
  console.log("  obfuscated " + n + " script(s)");

  html = await minifyHtml(html, HTML_OPTS);
  console.log("  minified HTML/CSS");

  fs.writeFileSync(file, html, "utf8");
  console.log("  saved " + file);
}

(async () => {
  for (const f of FILES) {
    if (fs.existsSync(f)) await processFile(f);
    else console.warn("not found: " + f);
  }
  console.log("Done.");
})();
