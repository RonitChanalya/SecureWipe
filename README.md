# SecureWipe

SecureWipe is an offline secure data-wiping tool designed to make storage sanitization simple, verifiable, and accessible.

The project focuses on securely erasing data from storage devices while providing verifiable evidence that the sanitization process was completed. It is designed around the principles of **NIST SP 800-88** and is intended for scenarios such as device reuse, resale, recycling, and IT asset disposal.

## Overview

Deleting files or formatting a drive does not necessarily make the underlying data unrecoverable. SecureWipe provides a dedicated environment for performing storage-aware data sanitization without relying on the operating system installed on the target machine.

The system is designed to run through a **bootable Linux environment**, allowing disks to be detected and sanitized independently of the host operating system.

## Features

- Offline operation through a bootable environment
- Automatic storage device detection
- Support for HDD and SSD/NVMe sanitization workflows
- Storage-aware wiping methods
- Protection against accidental system/device selection
- Wipe progress and operation status
- Post-wipe verification
- Generation of wipe certificates
- Machine-readable operation records
- Designed with NIST SP 800-88 sanitization guidelines in mind

## Workflow

```text
Boot SecureWipe
      ↓
Detect Storage Devices
      ↓
Select Target Device
      ↓
Choose Sanitization Method
      ↓
Confirm Operation
      ↓
Secure Data Erasure
      ↓
Verification
      ↓
Generate Wipe Certificate
```

The generated certificate provides a record of the sanitization operation and can be retained for auditing or verification purposes.

## Why SecureWipe?

Devices are frequently stored instead of reused or recycled because users and organizations cannot easily verify whether sensitive information has actually been removed.

SecureWipe explores a simple idea:

> Data erasure should not only be secure. It should also be verifiable.

By combining storage sanitization, verification, and certification into a single offline workflow, the project aims to make secure device disposal more practical and trustworthy.

## Use Cases

SecureWipe can be useful when preparing devices for:

- E-waste recycling
- Resale or donation
- IT asset decommissioning
- Device refurbishment
- Internal hardware reuse
- Secure disposal of storage media

## Security Considerations

SecureWipe performs destructive storage operations. Once a wipe operation has been successfully completed, the affected data may be permanently unrecoverable.

Always verify the selected storage device before starting an operation and back up any required data beforehand.

Different storage technologies require different sanitization approaches. In particular, flash-based devices such as SSDs and NVMe drives should not be treated identically to traditional HDDs due to mechanisms such as wear leveling and remapped storage blocks.

## Standards

The project is designed with reference to:

**NIST SP 800-88 — Guidelines for Media Sanitization**

The appropriate sanitization technique depends on the storage technology, device capabilities, and required level of assurance.

## Project Background

SecureWipe was developed as a solution for secure and trustworthy IT asset recycling.

The project was selected after a competitive screening round involving **250+ teams nationwide**, earning a place in the **36-hour onsite finals of the Samartha National Level Hackathon 2025**.

## Disclaimer

SecureWipe is an academic/prototype project intended for research, experimentation, and development purposes.

Secure data destruction is inherently destructive. Users are responsible for verifying the target device and ensuring that important data has been backed up before performing any wipe operation.
