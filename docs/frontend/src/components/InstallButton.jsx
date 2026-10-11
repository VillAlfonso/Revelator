import React, { useEffect, useState } from 'react';
import { canInstall, isIos, isStandalone, onInstallAvailable, promptInstall } from '../pwa';

/**
 * "Install App" button for the PWA.
 *
 * Renders nothing unless the browser actually offers an install path, so it
 * never shows a dead button:
 *  - Chrome / Edge / Samsung Internet -> fires beforeinstallprompt, we show the
 *    native dialog.
 *  - iOS Safari -> no prompt API exists, so we show the manual Share sheet
 *    instructions instead.
 *  - Already installed, or a browser with no support -> hidden.
 */
export default function InstallButton() {
  const [available, setAvailable] = useState(canInstall());
  const [installed, setInstalled] = useState(isStandalone());
  const [showIosHelp, setShowIosHelp] = useState(false);

  useEffect(() => onInstallAvailable(setAvailable), []);

  if (installed || isStandalone()) return null;

  const ios = isIos();
  if (!available && !ios) return null;

  const btnStyle = {
    display: 'inline-flex', alignItems: 'center', gap: 8,
    fontSize: 12, letterSpacing: 1, color: '#00ff66',
    border: '1px solid #1d3825', borderRadius: 4,
    padding: '10px 16px', cursor: 'pointer',
    background: 'rgba(0,255,102,0.04)',
  };

  const handleClick = async () => {
    if (ios && !available) {
      setShowIosHelp(v => !v);
      return;
    }
    const outcome = await promptInstall();
    if (outcome === 'accepted') setInstalled(true);
  };

  return (
    <div>
      <button type="button" className="mono" style={btnStyle} onClick={handleClick}>
        ⊕ Install App
      </button>
      <p className="mono" style={{ fontSize: 9, color: '#3f6e4a', marginTop: 8, letterSpacing: 1 }}>
        {ios && !available
          ? 'iPhone / iPad • adds Revelator to your home screen'
          : 'Adds Revelator to your home screen • no store needed'}
      </p>
      {showIosHelp && (
        <p className="mono" style={{ fontSize: 10, color: '#86efac', marginTop: 4, lineHeight: 1.6 }}>
          In Safari, tap the Share button, then "Add to Home Screen".
        </p>
      )}
    </div>
  );
}
