/** Non-render utility for unique filenames/ids (avoids react-hooks/purity on impure calls). */
export function randomUploadFilename(ext = 'jpg') {
  return `${Date.now()}-${Math.random().toString(36).slice(2)}.${ext}`;
}

export function markResetPasswordSent() {
  localStorage.setItem('last_reset_password_sent', Date.now().toString());
}
