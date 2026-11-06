/**
 * Security QR Code Verification Scanner
 * Mobile-first browser scanner with instant Supabase verification
 */

(() => {
  // DOM Elements
  const startSection = document.getElementById('start-section');
  const scannerSection = document.getElementById('scanner-section');
  const loadingSection = document.getElementById('loading-section');
  const resultSection = document.getElementById('result-section');

  const btnStartScan = document.getElementById('btn-start-scan');
  const btnStopScan = document.getElementById('btn-stop-scan');
  const btnScanAgain = document.getElementById('btn-scan-again');
  const btnSwitchCamera = document.getElementById('btn-switch-camera');
  const btnToggleTorch = document.getElementById('btn-toggle-torch');

  const resultIconContainer = document.getElementById('result-icon-container');
  const resultTitle = document.getElementById('result-title');
  const cardTypeBadge = document.getElementById('card-type-badge');
  const resultCardType = document.getElementById('result-card-type');
  const resultCardTypeIcon = document.getElementById('result-card-type-icon');
  const cardNumberBadge = document.getElementById('card-number-badge');
  const resultCardNumber = document.getElementById('result-card-number');
  const resultMessage = document.getElementById('result-message');
  const resultMeta = document.getElementById('result-meta');
  const resultMetaText = document.getElementById('result-meta-text');

  // Scanner State
  let html5QrCode = null;
  let isScanning = false;
  let isProcessing = false;
  let currentCameraId = null;
  let availableCameras = [];
  let currentCameraIndex = 0;
  let isTorchOn = false;

  // Web Audio Context for Instant Sound Feedback
  let audioCtx = null;

  function initAudioContext() {
    if (!audioCtx) {
      const AudioContext = window.AudioContext || window.webkitAudioContext;
      if (AudioContext) {
        audioCtx = new AudioContext();
      }
    }
    if (audioCtx && audioCtx.state === 'suspended') {
      audioCtx.resume();
    }
  }

  function playSuccessSound() {
    try {
      initAudioContext();
      if (!audioCtx) return;

      const now = audioCtx.currentTime;
      // High pleasant two-tone chime
      const osc1 = audioCtx.createOscillator();
      const osc2 = audioCtx.createOscillator();
      const gain = audioCtx.createGain();

      osc1.type = 'sine';
      osc2.type = 'sine';

      osc1.frequency.setValueAtTime(587.33, now); // D5
      osc1.frequency.setValueAtTime(880.00, now + 0.1); // A5

      gain.gain.setValueAtTime(0.25, now);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.35);

      osc1.connect(gain);
      gain.connect(audioCtx.destination);

      osc1.start(now);
      osc1.stop(now + 0.35);
    } catch (e) {
      console.warn('Audio play error:', e);
    }
  }

  function playErrorSound() {
    try {
      initAudioContext();
      if (!audioCtx) return;

      const now = audioCtx.currentTime;
      const osc = audioCtx.createOscillator();
      const gain = audioCtx.createGain();

      osc.type = 'sawtooth';
      osc.frequency.setValueAtTime(220, now);
      osc.frequency.setValueAtTime(160, now + 0.12);

      gain.gain.setValueAtTime(0.3, now);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.35);

      osc.connect(gain);
      gain.connect(audioCtx.destination);

      osc.start(now);
      osc.stop(now + 0.35);
    } catch (e) {
      console.warn('Audio play error:', e);
    }
  }

  function triggerVibrate(pattern) {
    if ('vibrate' in navigator) {
      try {
        navigator.vibrate(pattern);
      } catch (e) {
        // Ignore vibration errors
      }
    }
  }

  // Section Switching Helper
  function switchView(activeElement) {
    [startSection, scannerSection, loadingSection, resultSection].forEach((el) => {
      if (el) el.classList.remove('active');
    });
    if (activeElement) {
      activeElement.classList.add('active');
    }
  }

  // Format Card Number (e.g. 1 -> "001", 42 -> "042")
  function formatCardNumber(num) {
    if (num === null || num === undefined) return '---';
    return String(num).padStart(3, '0');
  }

  // Format Date to Arabic Locale (Asia/Aden Timezone)
  function formatTimestamp(timestampStr) {
    if (!timestampStr) return '';

    try {
      let isoStr = String(timestampStr).trim();

      // Ensure UTC interpretation if no timezone indicator is present
      // (PostgreSQL/Supabase timestamp without time zone returns strings like "2026-09-01T02:00:00")
      if (!/Z$/i.test(isoStr) && !/[+-]\d{2}(:\d{2})?$/.test(isoStr)) {
        isoStr = isoStr.replace(' ', 'T') + 'Z';
      }

      const date = new Date(isoStr);

      if (isNaN(date.getTime())) {
        return timestampStr;
      }

      return date.toLocaleString('ar-SA', {
        timeZone: 'Asia/Aden',
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: true
      });

    } catch (e) {
      return timestampStr;
    }
  }

  // ==========================================================================
  // QR Scanner Controller
  // ==========================================================================

  async function startScanner() {
    initAudioContext();
    switchView(scannerSection);
    isProcessing = false;

    try {
      if (!html5QrCode) {
        html5QrCode = new Html5Qrcode('qr-reader');
      }

      // Enumerate cameras if not already done
      if (availableCameras.length === 0) {
        try {
          const devices = await Html5Qrcode.getCameras();
          if (devices && devices.length) {
            availableCameras = devices;
            // Prefer back/environment camera
            const backCam = devices.find(d =>
              d.label.toLowerCase().includes('back') ||
              d.label.toLowerCase().includes('rear') ||
              d.label.toLowerCase().includes('environment')
            );
            currentCameraId = backCam ? backCam.id : devices[0].id;
            currentCameraIndex = devices.findIndex(d => d.id === currentCameraId);
          }
        } catch (e) {
          console.warn('Could not enumerate cameras, falling back to facingMode:', e);
        }
      }

      const cameraConfig = currentCameraId
        ? { deviceId: { exact: currentCameraId } }
        : { facingMode: 'environment' };

      const scanConfig = {
        fps: 15,
        qrbox: { width: 250, height: 250 },
        aspectRatio: 1.0,
        experimentalFeatures: {
          useBarCodeDetectorIfSupported: true
        }
      };

      await html5QrCode.start(
        cameraConfig,
        scanConfig,
        onScanSuccess,
        onScanError
      );

      isScanning = true;

      // Check if torch/flashlight is supported
      checkTorchSupport();

    } catch (err) {
      console.error('Camera startup error:', err);
      showNetworkOrPermissionError('تعذر تشغيل الكاميرا', 'يرجى التأكد من منح الإذن للكاميرا في المتصفح');
    }
  }

  async function stopScanner() {
    if (html5QrCode && isScanning) {
      try {
        await html5QrCode.stop();
      } catch (err) {
        console.warn('Error stopping scanner:', err);
      }
      isScanning = false;
    }
  }

  async function toggleTorch() {
    if (!html5QrCode || !isScanning) return;
    try {
      isTorchOn = !isTorchOn;
      await html5QrCode.applyVideoConstraints({
        advanced: [{ torch: isTorchOn }]
      });
      btnToggleTorch.classList.toggle('active', isTorchOn);
    } catch (e) {
      console.warn('Torch toggle not supported:', e);
    }
  }

  async function checkTorchSupport() {
    try {
      const track = html5QrCode.getRunningTrackCameraCapabilities();
      if (track && track.torchFeature && track.torchFeature().isSupported()) {
        btnToggleTorch.style.display = 'inline-flex';
      } else {
        btnToggleTorch.style.display = 'none';
      }
    } catch (e) {
      btnToggleTorch.style.display = 'none';
    }
  }

  async function switchCamera() {
    if (availableCameras.length <= 1) return;
    await stopScanner();
    currentCameraIndex = (currentCameraIndex + 1) % availableCameras.length;
    currentCameraId = availableCameras[currentCameraIndex].id;
    await startScanner();
  }

  // ==========================================================================
  // QR Detection & Verification
  // ==========================================================================

  function onScanSuccess(decodedText) {
    if (isProcessing) return;
    isProcessing = true;

    // Immediately stop scanning to prevent duplicate requests
    stopScanner();

    // Clean scanned text
    const token = (decodedText || '').trim();
    if (!token) {
      isProcessing = false;
      startScanner();
      return;
    }

    // Verify token with backend
    verifyToken(token);
  }

  function onScanError(errorMessage) {
    // Normal frame-by-frame scanning noise, ignore
  }

  async function verifyToken(token) {
    switchView(loadingSection);

    try {
      const response = await fetch('/api/verify', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'application/json'
        },
        body: JSON.stringify({ token })
      });

      const data = await response.json();

      if (!response.ok && !data.reason) {
        throw new Error(`Server returned ${response.status}`);
      }

      handleVerificationResult(data);

    } catch (error) {
      console.error('Verification error:', error);
      handleNetworkError();
    }
  }

  // ==========================================================================
  // Display Result Handlers
  // ==========================================================================

  // Card Type Configurations (Arabic Labels & Luxury Theme Icons)
  const CARD_TYPE_CONFIG = {
    NORMAL: {
      label: 'بطاقة عادية',
      className: 'type-normal',
      iconSvg: `
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
          <circle cx="12" cy="7" r="4"/>
        </svg>
      `
    },
    VIP: {
      label: 'بطاقة VIP',
      className: 'type-vip',
      iconSvg: `
        <svg viewBox="0 0 24 24" fill="currentColor">
          <path d="M12 2l2.4 6.6 7 .2-5.4 4.5 1.9 6.7-5.9-4-5.9 4 1.9-6.7-5.4-4.5 7-.2z"/>
        </svg>
      `
    },
    CHILD: {
      label: 'بطاقة أطفال',
      className: 'type-child',
      iconSvg: `
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="12" r="10"/>
          <path d="M8 14s1.5 2 4 2 4-2 4-2"/>
          <line x1="9" y1="9" x2="9.01" y2="9"/>
          <line x1="15" y1="9" x2="15.01" y2="9"/>
        </svg>
      `
    }
  };

  function renderCardType(cardType) {
    if (!cardTypeBadge) return;

    const normalized = typeof cardType === 'string' ? cardType.trim().toUpperCase() : '';
    const config = CARD_TYPE_CONFIG[normalized];

    // Reset previous type styling classes
    cardTypeBadge.classList.remove('type-normal', 'type-vip', 'type-child');

    if (config) {
      cardTypeBadge.classList.add(config.className);
      if (resultCardType) {
        resultCardType.textContent = config.label;
      }
      if (resultCardTypeIcon) {
        resultCardTypeIcon.innerHTML = config.iconSvg;
      }
      cardTypeBadge.style.display = 'inline-flex';
    } else {
      cardTypeBadge.style.display = 'none';
      if (resultCardType) {
        resultCardType.textContent = '';
      }
      if (resultCardTypeIcon) {
        resultCardTypeIcon.innerHTML = '';
      }
    }
  }

  function resetResultBoxClasses() {
    resultSection.classList.remove('state-valid', 'state-already-used', 'state-invalid', 'state-network-error');
    renderCardType(null);
  }

  function handleVerificationResult(data) {
    resetResultBoxClasses();
    switchView(resultSection);

    // CASE 1: Valid Card
    if (data.valid === true) {
      resultSection.classList.add('state-valid');

      resultIconContainer.innerHTML = `
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="20 6 9 17 4 12"/>
        </svg>
      `;

      resultTitle.textContent = '✓ البطاقة صالحة';

      renderCardType(data.card_type);

      cardNumberBadge.style.display = 'flex';
      resultCardNumber.textContent = formatCardNumber(data.card_number);

      resultMessage.textContent = 'تم تسجيل الدخول بنجاح';

      if (data.scanned_at) {
        resultMeta.style.display = 'inline-flex';
        resultMetaText.textContent = `تاريخ المسح: ${formatTimestamp(data.scanned_at)}`;
      } else {
        resultMeta.style.display = 'none';
      }

      playSuccessSound();
      triggerVibrate([80, 50, 80]);
      return;
    }

    // CASE 2: Card Already Used
    if (data.reason === 'ALREADY_USED') {
      resultSection.classList.add('state-already-used');

      resultIconContainer.innerHTML = `
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
          <line x1="18" y1="6" x2="6" y2="18"/>
          <line x1="6" y1="6" x2="18" y2="18"/>
        </svg>
      `;

      resultTitle.textContent = '✕ البطاقة مستخدمة مسبقًا';

      renderCardType(data.card_type);

      if (data.card_number !== undefined && data.card_number !== null) {
        cardNumberBadge.style.display = 'flex';
        resultCardNumber.textContent = formatCardNumber(data.card_number);
      } else {
        cardNumberBadge.style.display = 'none';
      }

      if (data.scanned_at) {
        resultMessage.textContent = 'تم استخدام هذه البطاقة للدخول مسبقًا';
        resultMeta.style.display = 'inline-flex';
        resultMetaText.textContent = `تم استخدامها بتاريخ: ${formatTimestamp(data.scanned_at)}`;
      } else {
        resultMessage.textContent = 'تم استخدام هذه البطاقة مسبقًا';
        resultMeta.style.display = 'none';
      }

      playErrorSound();
      triggerVibrate([200, 100, 200]);
      return;
    }

    // CASE 3: Invalid Card (NOT_FOUND or other)
    resultSection.classList.add('state-invalid');

    resultIconContainer.innerHTML = `
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="12" cy="12" r="10"/>
        <line x1="15" y1="9" x2="9" y2="15"/>
        <line x1="9" y1="9" x2="15" y2="15"/>
      </svg>
    `;

    resultTitle.textContent = '✕ بطاقة غير صالحة';
    cardNumberBadge.style.display = 'none';
    resultMessage.textContent = 'رمز QR غير موجود في النظام';
    resultMeta.style.display = 'none';

    playErrorSound();
    triggerVibrate([250]);
  }

  // CASE 4: Network / Server Error
  function handleNetworkError() {
    resetResultBoxClasses();
    switchView(resultSection);

    resultSection.classList.add('state-network-error');

    resultIconContainer.innerHTML = `
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
        <line x1="12" y1="9" x2="12" y2="13"/>
        <line x1="12" y1="17" x2="12.01" y2="17"/>
      </svg>
    `;

    resultTitle.textContent = 'تعذر الاتصال بالنظام';
    cardNumberBadge.style.display = 'none';
    resultMessage.textContent = 'تأكد من اتصال الإنترنت وحاول مرة أخرى';
    resultMeta.style.display = 'none';

    playErrorSound();
    triggerVibrate([100, 50, 100, 50, 100]);
  }

  function showNetworkOrPermissionError(title, msg) {
    resetResultBoxClasses();
    switchView(resultSection);

    resultSection.classList.add('state-network-error');
    resultIconContainer.innerHTML = `
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/>
        <circle cx="12" cy="13" r="4"/>
        <line x1="1" y1="1" x2="23" y2="23"/>
      </svg>
    `;

    resultTitle.textContent = title;
    cardNumberBadge.style.display = 'none';
    resultMessage.textContent = msg;
    resultMeta.style.display = 'none';
  }

  // ==========================================================================
  // Event Listeners
  // ==========================================================================

  btnStartScan.addEventListener('click', () => {
    startScanner();
  });

  btnStopScan.addEventListener('click', async () => {
    await stopScanner();
    switchView(startSection);
  });

  btnScanAgain.addEventListener('click', () => {
    startScanner();
  });

  btnSwitchCamera.addEventListener('click', () => {
    switchCamera();
  });

  btnToggleTorch.addEventListener('click', () => {
    toggleTorch();
  });

  // Handle page visibility change to release camera if tab minimized
  document.addEventListener('visibilitychange', () => {
    if (document.hidden && isScanning) {
      stopScanner();
      switchView(startSection);
    }
  });

})();
