export function generateUUIDv7(): string {
  const timestamp = Date.now();
  const timeHex = timestamp.toString(16).padStart(12, '0');
  const timeHigh = timeHex.slice(0, 8);
  const timeMid = timeHex.slice(8, 12);

  // Generate random bytes for version and random bits
  const randomBytes = new Uint8Array(10);
  if (typeof crypto !== 'undefined' && crypto.getRandomValues) {
    crypto.getRandomValues(randomBytes);
  } else {
    for (let i = 0; i < 10; i++) {
      randomBytes[i] = Math.floor(Math.random() * 256);
    }
  }

  // Version 7 in high nibble of time_hi_and_version
  const randA = ((randomBytes[0] << 8) | randomBytes[1]) & 0x0fff;
  const verAndRand = (0x7000 | randA).toString(16).padStart(4, '0');

  // Variant 10xx in high 2 bits of clock_seq_hi_and_reserved
  const randB = (randomBytes[2] & 0x3f) | 0x80;
  const varAndRand = randB.toString(16).padStart(2, '0');

  const rest = Array.from(randomBytes.slice(3))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');

  return `${timeHigh}-${timeMid}-${verAndRand}-${varAndRand}${randomBytes[3].toString(16).padStart(2, '0')}-${rest.slice(2)}`;
}
