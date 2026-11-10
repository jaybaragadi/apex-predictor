// Convert the single-file Vite build into an Artifact page body: the hosting
// skeleton supplies <!doctype>, <html>, <head> and <body>, so strip them and
// keep title/meta/links/styles/scripts plus the root element.
import { readFileSync, writeFileSync } from "node:fs";
const html = readFileSync(new URL("../dist-artifact/index.html", import.meta.url), "utf8");
const head = html.match(/<head>([\s\S]*?)<\/head>/)[1]
  .replace(/<meta charset[^>]*>/i, "")
  .replace(/<meta name="viewport"[^>]*>/i, "");
const body = html.match(/<body>([\s\S]*?)<\/body>/)[1];
// module scripts are deferred; keep them after #root
const title = head.match(/<title>[\s\S]*?<\/title>/)[0];
const rest = head.replace(title, "");
const out = `${title}\n${rest.trim()}\n${body.trim()}\n`;
writeFileSync(new URL("../dist-artifact/apex-predictor.html", import.meta.url), out);
console.log("artifact page:", (out.length / 1024).toFixed(0), "KB");
