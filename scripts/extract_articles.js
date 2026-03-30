#!/usr/bin/env node
/**
 * Extract articles from articles.ts and output as JSON to stdout.
 * Run from project root: node scripts/extract_articles.js
 */
const fs = require("fs");
const path = require("path");

// Inline config lookups (mirrored from webapp/src/lib/*.ts)
const ageBadgeConfig = {
  "45_beginner": { label: "45+ újrakezdő", className: "bg-sky-100 text-sky-700 border border-sky-300" },
  "45_advanced": { label: "45+ haladó", className: "bg-sky-200 text-sky-800 border border-sky-400" },
  "50_active": { label: "50+ aktív", className: "bg-violet-100 text-violet-700 border border-violet-300" },
  "50_pro": { label: "50+ profi", className: "bg-violet-200 text-violet-800 border border-violet-400" },
  "55_veteran": { label: "55+ veterán", className: "bg-amber-100 text-amber-700 border border-amber-300" },
};

const recoveryTimeConfig = {
  light: { label: "24ó regeneráció", className: "bg-teal-50 text-teal-700 border border-teal-200" },
  moderate: { label: "36ó pihenő", className: "bg-amber-50 text-amber-700 border border-amber-200" },
  intense: { label: "48ó regeneráció", className: "bg-rose-50 text-rose-700 border border-rose-200" },
};

const priceBadgeConfig = {
  budget: { label: "💰 Budget", className: "bg-emerald-100 text-emerald-700 border border-emerald-200" },
  mid: { label: "⭐ Középkategória", className: "bg-sky-100 text-sky-700 border border-sky-200" },
  premium: { label: "💎 Prémium", className: "bg-amber-100 text-amber-700 border border-amber-200" },
};

const intensityZoneConfig = {
  z1: { zone: "Z1", description: "Regenerációs zóna", className: "bg-slate-100 text-slate-600 border border-slate-300" },
  z2: { zone: "Z2", description: "Alap állóképesség", className: "bg-green-50 text-green-700 border border-green-200" },
  z3: { zone: "Z3", description: "Aerob tempó", className: "bg-yellow-50 text-yellow-700 border border-yellow-300" },
  z4: { zone: "Z4", description: "Laktát küszöb", className: "bg-orange-50 text-orange-700 border border-orange-300" },
  z5: { zone: "Z5", description: "Maximális erőfeszítés", className: "bg-red-50 text-red-700 border border-red-200" },
};

const articlesPath = path.join(__dirname, "..", "webapp", "src", "data", "articles.ts");
let content = fs.readFileSync(articlesPath, "utf8");

// Find where the articles array starts
const arrayStart = content.indexOf("export const articles");
if (arrayStart === -1) {
  process.stderr.write("Could not find articles array\n");
  process.exit(1);
}

// Extract just the array section, strip TS type annotation and export keyword
let arraySection = content.substring(arrayStart);
arraySection = arraySection.replace(/^export\s+/, "");
arraySection = arraySection.replace(/:\s*Article\[\]/, "");

// Execute in a function scope with config vars injected
const fn = new Function(
  "ageBadgeConfig",
  "recoveryTimeConfig",
  "priceBadgeConfig",
  "intensityZoneConfig",
  arraySection + "\nreturn articles;"
);

try {
  const articles = fn(ageBadgeConfig, recoveryTimeConfig, priceBadgeConfig, intensityZoneConfig);
  process.stdout.write(JSON.stringify(articles, null, 2) + "\n");
} catch (e) {
  process.stderr.write("Error evaluating articles: " + e.message + "\n");
  process.exit(1);
}
