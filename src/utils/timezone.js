export function getBrowserTimezone() {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
  } catch {
    return 'UTC';
  }
}

export function isValidTimezone(timezone) {
  if (!timezone || typeof timezone !== 'string') return false;
  try {
    Intl.DateTimeFormat(undefined, { timeZone: timezone });
    return true;
  } catch {
    return false;
  }
}

export function resolveTimezone(timezone) {
  if (isValidTimezone(timezone)) return timezone;
  return 'UTC';
}

function getZonedParts(date, timeZone) {
  // hourCycle h23 avoids the hour="24" midnight quirk that shifts days backward.
  const formatter = new Intl.DateTimeFormat('en-US', {
    timeZone,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hourCycle: 'h23',
  });

  const parts = formatter.formatToParts(date);
  const get = (type) => parts.find((p) => p.type === type)?.value ?? '0';
  const hourRaw = Number(get('hour'));

  return {
    year: Number(get('year')),
    month: Number(get('month')),
    day: Number(get('day')),
    hour: Number.isFinite(hourRaw) ? hourRaw % 24 : 0,
    minute: Number(get('minute')),
    second: Number(get('second')),
  };
}

function zonedDateTimeToUtc({ year, month, day, hour = 0, minute = 0, second = 0 }, timeZone) {
  let utcGuess = Date.UTC(year, month - 1, day, hour, minute, second);

  for (let i = 0; i < 2; i++) {
    const parts = getZonedParts(new Date(utcGuess), timeZone);
    const asIfUtc = Date.UTC(
      parts.year,
      parts.month - 1,
      parts.day,
      parts.hour,
      parts.minute,
      parts.second
    );
    const intended = Date.UTC(year, month - 1, day, hour, minute, second);
    utcGuess += intended - asIfUtc;
  }

  return new Date(utcGuess);
}

function addDaysToZonedDate({ year, month, day }, days, timeZone) {
  const noon = zonedDateTimeToUtc({ year, month, day, hour: 12 }, timeZone);
  const shifted = new Date(noon.getTime() + days * 86400000);
  const parts = getZonedParts(shifted, timeZone);
  return { year: parts.year, month: parts.month, day: parts.day };
}

/** ISO UTC string for local midnight + N days in the given IANA timezone. */
export function nextLocalMidnightUtc(timeZone, daysFromNow = 1) {
  const tz = resolveTimezone(timeZone);
  const nowParts = getZonedParts(new Date(), tz);
  const target = addDaysToZonedDate(nowParts, daysFromNow, tz);
  return zonedDateTimeToUtc({ ...target, hour: 0, minute: 0, second: 0 }, tz).toISOString();
}

export function getEffectiveTimezone(profileData) {
  const browserTz = getBrowserTimezone();
  if (profileData?.timezone && isValidTimezone(profileData.timezone) && profileData.timezone !== 'UTC') {
    return profileData.timezone;
  }
  return browserTz;
}

export async function ensureProfileTimezone(supabase, userId, profileData) {
  const effective = getEffectiveTimezone(profileData);

  if (profileData && profileData.timezone !== effective) {
    const { error } = await supabase
      .from('profiles')
      .update({ timezone: effective })
      .eq('id', userId);

    if (!error) {
      profileData.timezone = effective;
    }
  }

  return effective;
}
