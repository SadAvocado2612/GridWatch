const fs = require('fs');
const path = require('path');

const publishDir = path.join(__dirname, 'frontend');
const redirectsFile = path.join(publishDir, '_redirects');

// Determine backend URL from environment variables
const backendUrl = process.env.API_URL || process.env.BACKEND_API_URL || 'http://localhost:8000';

console.log(`[Netlify Build] Configuring backend API redirection to: ${backendUrl}`);

const redirectsContent = `/api/*  ${backendUrl.replace(/\/$/, '')}/api/:splat  200!\n`;

fs.writeFileSync(redirectsFile, redirectsContent, 'utf8');

console.log('[Netlify Build] Successfully wrote frontend/_redirects file.');
console.log(`[Netlify Build] Redirect file content: ${redirectsContent.trim()}`);
