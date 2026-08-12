export function isPastSlot(utcIso: string): boolean {
  return new Date(utcIso).getTime() < Date.now();
}

export function isWithinLockout(utcIso: string): boolean {
  const msUntilSlot = new Date(utcIso).getTime() - Date.now();
  return msUntilSlot < 2 * 60 * 60 * 1000;
}

export function utcToLocalDateTime(utcIso: string): string {
  return new Date(utcIso).toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

export function localDateTimeToUtc(date: string, time: string): string {
  const localDateTime = new Date(`${date}T${time}`);
  return new Date(localDateTime.getTime() - localDateTime.getTimezoneOffset() * 60000).toISOString();
}
