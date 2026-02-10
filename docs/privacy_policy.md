---
layout: default
title: Privacy Policy
nav_order: 10
---

# Privacy Policy

This Privacy Policy describes how your information is handled when you use the Google Sheets Bayesian Optimization Integration ("the Service").

## 1. Data Collection and Storage
The Service is designed to be **stateless** and does not store any Google user data.

- **Optimization Data:** All parameter configurations and objective values reside exclusively within your Google Sheet. The Service receives this data only for the duration of processing a single optimization request and immediately discards it after generating the response.

- **In-Memory Processing:** Data sent to the Cloud Run service is processed entirely in-memory to generate optimization suggestions. Once the response is returned to your Google Sheet, all data is immediately discarded from memory.

- **No Persistent Storage:** We do not store, retain, save, or harvest any optimization data, spreadsheet content, or user-generated information in any database, file system, or persistent storage mechanism.

## 2. Data Sharing, Transfer, and Disclosure

**We do not share, transfer, sell, or disclose any Google user data to third parties.**

- **No Third-Party Sharing:** Your optimization data, spreadsheet content, and objective values are never shared with, transferred to, or disclosed to any third-party services, partners, advertisers, or other entities.

- **No Cross-User Data Sharing:** Data from one user is never accessible to or shared with any other user of the Service.

- **Service Provider:** The Service operates on Google Cloud Platform infrastructure. Your data is processed within Google's secure infrastructure and is not transferred outside of the Google Cloud Platform environment during processing.

## 3. Data Protection and Security

The Service implements multiple layers of security to protect your data:

- **Transmission Security:** All data transmitted between your Google Sheet and our Cloud Run service is encrypted in transit using HTTPS/TLS protocols.

- **Authentication:** Access to the Service requires authentication via your Google account. Only authenticated users can submit optimization requests.

- **In-Memory Only Processing:** Since no data is persisted to disk or databases, there is no stored data that could be compromised. All processing occurs in secure, ephemeral memory.

- **Rate Limiting:** The Service implements rate limiting to prevent abuse and protect against unauthorized access attempts.

- **No Logging of Sensitive Data:** Our application logs do not contain any user data, optimization parameters, objective values, or spreadsheet content. Logs only contain non-sensitive metadata such as request timestamps, response status codes, and request durations for operational monitoring.

## 4. Data Retention and Deletion

**The Service does not retain any Google user data.**

- **Zero Retention Period:** Since no user data is stored persistently, there is no data retention period. All data exists only temporarily in memory during request processing (typically less than a few seconds) and is automatically discarded when the response is sent.

- **No Manual Deletion Required:** Because we don't store any user data, you do not need to request deletion of your data. There is no data to delete.

- **Automatic Purging:** Any data that enters our system during a request is automatically purged from memory immediately after the optimization response is generated.

## 5. Authentication and Identity

The Service uses your Google account email address solely for authentication and access control:

- We validate your email address to ensure you are an authorized user.
- Your email address is used only for rate limiting and authentication purposes during your active session.
- We do not build user profiles, track usage patterns across sessions, or share your identity with third parties.
- Your email address is not stored persistently and exists only in memory during request processing.

## 6. Third-Party Services

The Service operates on Google Cloud Platform and integrates with Google Sheets:

- Your use of Google Cloud Platform and Google Sheets is governed by Google's Privacy Policy.
- The Service does not integrate with or share data with any other third-party services beyond the Google ecosystem required for operation (Google Cloud Run and Google Sheets API).

## 7. Your Data Rights

Since we do not store any of your data:

- **Access:** We cannot provide copies of your data because we don't retain it. All your data remains in your Google Sheet.
- **Deletion:** No deletion is necessary as no data is retained.
- **Portability:** All your data remains in your Google Sheet and is fully portable.
- **Control:** You maintain complete control over your data in your Google Sheet at all times.


## 8. Contact

If you have questions about this Privacy Policy, please contact us through the GitHub repository associated with this project.

**Last Updated:** February 9, 2026
