#!/usr/bin/env node

const { execFileSync } = require("child_process");
const path = require("path");

const installScript = path.join(__dirname, "..", "install.sh");
const args = process.argv.slice(2);

try {
  execFileSync("bash", [installScript, ...args], { stdio: "inherit" });
} catch (e) {
  process.exit(e.status || 1);
}
