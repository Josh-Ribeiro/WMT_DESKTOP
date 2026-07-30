import { describe, expect, it } from "vitest";
import {
  explicitDeviceType,
  isIpv4Address,
  isReservedPrinterIp,
  searchDeviceType,
} from "./deviceType";

describe("printer network classification", () => {
  it("classifies the complete reserved printer range", () => {
    expect(isReservedPrinterIp("10.131.200.0")).toBe(false);
    expect(isReservedPrinterIp("10.131.200.1")).toBe(true);
    expect(isReservedPrinterIp("10.131.200.254")).toBe(true);
    expect(isReservedPrinterIp("10.131.200.255")).toBe(true);
    expect(isReservedPrinterIp("10.131.201.1")).toBe(false);
  });

  it("honors the device type reported by the backend", () => {
    expect(searchDeviceType("PRINT-SALA-01", "printer")).toBe("printer");
    expect(searchDeviceType("WKS001", "workstation")).toBe("workstation");
    expect(searchDeviceType("WKS001", "printer")).toBe("workstation");
    expect(searchDeviceType("10.131.200.50")).toBe("printer");
  });

  it("treats WKS hostnames and every valid IP as explicit device searches", () => {
    expect(explicitDeviceType("wks048-123br")).toBe("workstation");
    expect(explicitDeviceType("10.131.200.50")).toBe("printer");
    expect(explicitDeviceType("10.131.201.50")).toBe("workstation");
    expect(explicitDeviceType("192.168.10.20")).toBe("workstation");
    expect(explicitDeviceType("ribeiro.josue")).toBeNull();
    expect(explicitDeviceType("ST7SILVALU")).toBeNull();
    expect(isIpv4Address("10.131.200.999")).toBe(false);
  });
});
