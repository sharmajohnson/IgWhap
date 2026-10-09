# Wiring Baily.exe up to the license server

Your app needs to do two things: ask the user for their key once, and quietly
re-check it afterwards. Drop this into the Electron app's main process.

```js
// licenseClient.js  (inside your Electron app's source, not this server)
const { machineIdSync } = require('node-machine-id'); // npm install node-machine-id
const Store = require('electron-store');               // npm install electron-store

const store = new Store();
const API_BASE = 'https://your-domain.com/api/license'; // your deployed server
const APP_KEY = 'test-appkey-456'; // same value as APP_API_KEY in the server's .env

const deviceId = machineIdSync(true);

async function activate(licenseKey) {
  const res = await fetch(`${API_BASE}/activate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-App-Key': APP_KEY },
    body: JSON.stringify({
      license_key: licenseKey,
      device_id: deviceId,
      device_name: require('os').hostname()
    })
  });
  const data = await res.json();
  if (data.ok) store.set('license_key', licenseKey);
  return data; // { ok, status, reason, expires_at, plan }
}

async function checkLicense() {
  const licenseKey = store.get('license_key');
  if (!licenseKey) return { ok: false, reason: 'no_key_saved' };

  try {
    const res = await fetch(`${API_BASE}/validate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-App-Key': APP_KEY },
      body: JSON.stringify({ license_key: licenseKey, device_id: deviceId })
    });
    return await res.json();
  } catch (e) {
    // Server unreachable (offline). Decide your own grace-period policy here,
    // e.g. allow launch if the last successful check was under 7 days ago.
    return { ok: false, reason: 'network_error' };
  }
}

module.exports = { activate, checkLicense };
```

Then in your app startup (e.g. `main.js`):

```js
const { checkLicense, activate } = require('./licenseClient');

app.whenReady().then(async () => {
  const result = await checkLicense();
  if (!result.ok) {
    // show your "Enter license key" screen, call activate(key) on submit
  } else {
    createMainWindow();
  }
});
```

### Notes

- `X-App-Key` just stops randoms from hitting the API directly — anyone who
  decompiles the .exe can read it, so it is not a secret in the security
  sense. The actual protection is the license key + device limit check.
- `device_id` is what enforces "max devices per license." `node-machine-id`
  gives a stable per-PC id; swap in whatever you prefer.
- Call `checkLicense()` on every app launch, and optionally every few hours
  while it's running, so a revoked key stops working promptly.
