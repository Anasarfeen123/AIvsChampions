"use strict";

const fs = require("fs");
const child_process = require("child_process");
const esbuild = require('esbuild');

const copyOverDataJSON = (file = 'data') => {
	try {
		if (!fs.existsSync(file)) return;
		const files = fs.readdirSync(file);
		for (const f of files) {
			const cur = `${file}/${f}`;
			try {
				if (fs.statSync(cur).isDirectory()) {
					copyOverDataJSON(cur);
				} else if (f.endsWith('.json')) {
					const dest = require('path').resolve('dist', cur);
					fs.mkdirSync(require('path').dirname(dest), { recursive: true });
					fs.copyFileSync(cur, dest);
				}
			} catch (err) {}
		}
	} catch (err) {}
};

const shouldBeCompiled = file => {
	if (file.includes('node_modules/')) return false;
	if (file.endsWith('.tsx')) return true;
	if (file.endsWith('.ts')) return !(file.endsWith('.d.ts') || file.includes('global'));
	return false;
};

const findFilesForPath = path => {
	const out = [];
	try {
		const files = fs.readdirSync(path);
		for (const file of files) {
			const cur = `${path}/${file}`;
			if (cur.includes('node_modules') || cur.includes("/logs") || cur.includes("/databases")) continue;
			try {
				if (fs.statSync(cur).isDirectory()) {
					out.push(...findFilesForPath(cur));
				} else if (shouldBeCompiled(cur)) {
					out.push(cur);
				}
			} catch (err) {}
		}
	} catch (err) {}
	return out;
};

exports.transpile = decl => {
	esbuild.buildSync({
		entryPoints: findFilesForPath('.'),
		outdir: './dist',
		outbase: '.',
		format: 'cjs',
		tsconfig: './tsconfig.json',
		sourcemap: true,
	});
	try {
		fs.mkdirSync('./dist/config', { recursive: true });
		if (fs.existsSync('./config/config-example.js')) {
			fs.copyFileSync('./config/config-example.js', './dist/config/config-example.js');
		}
	} catch (err) {}
	copyOverDataJSON();

	// NOTE: replace is asynchronous - add additional replacements for the same path in one call instead of making multiple calls.
	if (decl) {
		exports.buildDecls();
	}
};

exports.buildDecls = () => {
	try {
		child_process.execSync(`node ./node_modules/typescript/bin/tsc -p sim`, { stdio: 'inherit' });
	} catch {}
};
