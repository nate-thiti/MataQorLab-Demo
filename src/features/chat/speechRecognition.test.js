import { describe, expect, it } from 'vitest';
import {
  getSpeechRecognitionConstructor,
  joinSpeechTranscript,
  speechRecognitionErrorMessage,
} from './speechRecognition.js';

describe('speech recognition helpers', () => {
  it('joins existing input with final and interim speech without losing text', () => {
    expect(joinSpeechTranscript('สรุป', 'ยอดขายเดือนนี้', 'เทียบปีก่อน'))
      .toBe('สรุป ยอดขายเดือนนี้ เทียบปีก่อน');
  });

  it('does not add extra spaces for an empty base or transcript', () => {
    expect(joinSpeechTranscript('', 'hello', '')).toBe('hello');
    expect(joinSpeechTranscript('hello', '', '')).toBe('hello');
  });

  it('detects standard and webkit speech recognition constructors', () => {
    const standard = () => {};
    const webkit = () => {};
    expect(getSpeechRecognitionConstructor({ SpeechRecognition: standard })).toBe(standard);
    expect(getSpeechRecognitionConstructor({ webkitSpeechRecognition: webkit })).toBe(webkit);
    expect(getSpeechRecognitionConstructor({})).toBeNull();
  });

  it('returns localized permission errors', () => {
    expect(speechRecognitionErrorMessage('not-allowed', false)).toContain('อนุญาต');
    expect(speechRecognitionErrorMessage('not-allowed', true)).toContain('permission');
  });
});
