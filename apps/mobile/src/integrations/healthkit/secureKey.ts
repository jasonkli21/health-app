/** Encode arbitrary JavaScript strings into SecureStore's supported key alphabet. */
export function secureKeySegment(value: string): string {
  let encoded = "";
  for (let index = 0; index < value.length; index += 1) {
    encoded += value.charCodeAt(index).toString(16).padStart(4, "0");
  }
  return encoded;
}
