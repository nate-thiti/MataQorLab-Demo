export function joinSpeechTranscript(baseText = '', finalText = '', interimText = '') {
  const base = String(baseText || '').trim();
  const speech = `${String(finalText || '').trim()} ${String(interimText || '').trim()}`.trim();
  if (!base) return speech;
  if (!speech) return base;
  return `${base} ${speech}`;
}

export function getSpeechRecognitionConstructor(browserWindow) {
  if (!browserWindow) return null;
  return browserWindow.SpeechRecognition || browserWindow.webkitSpeechRecognition || null;
}

export function speechRecognitionErrorMessage(errorCode, isEn = false) {
  const messages = {
    'not-allowed': isEn
      ? 'Microphone permission was denied. Allow microphone access in your browser settings.'
      : 'ไม่ได้รับอนุญาตให้ใช้ไมโครโฟน กรุณาอนุญาตสิทธิ์ไมค์ในการตั้งค่าเบราว์เซอร์',
    'service-not-allowed': isEn
      ? 'Speech recognition is blocked by the browser or device policy.'
      : 'เบราว์เซอร์หรือนโยบายของอุปกรณ์บล็อกการรู้จำเสียง',
    'audio-capture': isEn
      ? 'No working microphone was found.'
      : 'ไม่พบไมโครโฟนที่พร้อมใช้งาน',
    network: isEn
      ? 'Speech recognition could not connect to the recognition service.'
      : 'ไม่สามารถเชื่อมต่อบริการแปลงเสียงเป็นข้อความได้',
    'language-not-supported': isEn
      ? 'Speech recognition does not support this language on your browser.'
      : 'เบราว์เซอร์นี้ยังไม่รองรับการรู้จำเสียงภาษาที่เลือก',
  };
  return messages[errorCode] || (
    isEn
      ? 'Speech recognition stopped unexpectedly. Please try again.'
      : 'การแปลงเสียงหยุดทำงาน กรุณาลองใหม่อีกครั้ง'
  );
}
