export type SearchDeviceType = "workstation" | "printer";

export function isIpv4Address(value: string): boolean {
  const octets = value
    .trim()
    .split(".")
    .map(part => (/^\d{1,3}$/.test(part) ? Number(part) : Number.NaN));

  return (
    octets.length === 4 &&
    octets.every(octet => Number.isInteger(octet) && octet >= 0 && octet <= 255)
  );
}

export function isReservedPrinterIp(value: string): boolean {
  if (!isIpv4Address(value)) return false;
  const octets = value.trim().split(".").map(Number);

  return (
    octets[0] === 10 && octets[1] === 131 && octets[2] === 200 && octets[3] >= 1
  );
}

export function explicitDeviceType(value: string): SearchDeviceType | null {
  const normalized = value.trim().toUpperCase();
  if (normalized.startsWith("WKS")) return "workstation";
  if (!isIpv4Address(normalized)) return null;
  return isReservedPrinterIp(normalized) ? "printer" : "workstation";
}

export function searchDeviceType(
  value: string,
  reportedType?: string
): SearchDeviceType {
  if (value.trim().toUpperCase().startsWith("WKS")) return "workstation";
  return reportedType === "printer" || isReservedPrinterIp(value)
    ? "printer"
    : "workstation";
}
