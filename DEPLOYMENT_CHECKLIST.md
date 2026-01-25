# Pre-Production Deployment Checklist

## Environment Setup
- [ ] Set `CLOUD_RUN_SERVICE_URL` environment variable
- [ ] Set `COMMIT_SHA` from git
- [ ] Verify all secrets are in Secret Manager (not in code)
- [ ] Enable Cloud Run API
- [ ] Enable Artifact Registry API

## Security
- [ ] Review all authentication code
- [ ] Test JWT validation with expired tokens
- [ ] Test rate limiting
- [ ] Verify input validation on all endpoints
- [ ] Run security scan: `gcloud container images scan`
- [ ] Enable Cloud Armor (optional, for DDoS protection)
- [ ] Set up VPC Service Controls (optional, for data exfiltration prevention)

## Testing
- [ ] Run all unit tests
- [ ] Run integration tests against Cloud Run
- [ ] Test with malformed inputs
- [ ] Load test with expected traffic
- [ ] Test authentication failure scenarios

## Monitoring
- [ ] Set up Cloud Logging
- [ ] Set up Cloud Monitoring alerts for:
  - [ ] Error rate > 5%
  - [ ] Latency > 10s
  - [ ] Authentication failures > 10/min
  - [ ] Rate limit hits > 100/min
- [ ] Configure uptime checks

## Documentation
- [ ] Update README with security considerations
- [ ] Document incident response plan
- [ ] Create user privacy policy
- [ ] Create terms of service

## Cloud Run Configuration
- [ ] `--no-allow-unauthenticated` is set
- [ ] Minimum instances = 0 (cost optimization)
- [ ] Maximum instances = 10 (prevent runaway costs)
- [ ] CPU throttling enabled
- [ ] Request timeout = 60s
- [ ] Memory = 512Mi
- [ ] Container runs as non-root user

## Final Steps
- [ ] Run `gcloud container images scan` on production image
- [ ] Deploy to staging environment first
- [ ] Perform smoke tests on staging
- [ ] Deploy to production
- [ ] Monitor for 24 hours
- [ ] Announce to users
