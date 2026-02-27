# GPU Host Provisioning Runbook (AFR-5)

This runbook provisions and validates a dedicated host for MAX Serve with an 8B model.

## Target Host Specification

- **GPU:** NVIDIA GeForce RTX 4090 (24 GB VRAM)
- **RAM:** 64 GB
- **Storage:** 500 GB NVMe SSD
- **Access:** SSH (key-based authentication)
- **OS:** Ubuntu 22.04 LTS (recommended baseline)

## Acceptance Criteria Mapping

| Story requirement | Verification command |
|---|---|
| RTX 4090 (24GB VRAM) | `nvidia-smi --query-gpu=name,memory.total --format=csv` |
| 64GB RAM | `free -h` |
| 500GB NVMe SSD | `lsblk -o NAME,SIZE,TYPE,MOUNTPOINT` |
| SSH access | `ssh -i <key> <user>@<host> 'echo ok'` |
| MAX Serve-ready runtime | `docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi` |

## Provisioning Steps

1. **Create host from provider image**
   - Ubuntu 22.04 LTS
   - Attach/allocate RTX 4090 profile
   - Configure root disk to 500GB NVMe
   - Add security group/firewall rules: allow only SSH (22) from trusted CIDRs

2. **Prepare SSH access**
   - Create non-root admin user
   - Add authorized public key
   - Disable password authentication in `/etc/ssh/sshd_config`
   - Optional hardening: disable root login

3. **Install NVIDIA stack**
   - Install latest stable NVIDIA driver compatible with RTX 4090
   - Install NVIDIA Container Toolkit
   - Reboot and validate with `nvidia-smi`

4. **Install container runtime**
   - Install Docker Engine and Docker Compose plugin
   - Add admin user to `docker` group
   - Enable Docker service at boot

5. **Clone and bootstrap brainego**
   ```bash
   git clone <repository-url>
   cd brainego
   chmod +x download_model.sh init.sh
   ./download_model.sh
   ./init.sh
   ```

6. **Validate MAX Serve operational health**
   ```bash
   curl http://localhost:8080/health
   curl http://localhost:8000/health
   nvidia-smi
   ```

## Post-Provision Validation Checklist

- [ ] `nvidia-smi` reports **NVIDIA GeForce RTX 4090** and ~24564 MiB memory
- [ ] `free -h` reports ~64Gi total memory
- [ ] `lsblk` reports an NVMe device ~500G
- [ ] SSH key auth works and password auth is disabled
- [ ] `docker run --rm --gpus all ... nvidia-smi` succeeds
- [ ] `init.sh` completes without errors
- [ ] `http://localhost:8080/health` returns healthy

## Suggested Handover Template

```text
Host: <fqdn-or-ip>
SSH User: <username>
GPU: NVIDIA GeForce RTX 4090 (24GB)
RAM: <reported total>
Disk: <nvme device + size>
Validation Date: <YYYY-MM-DD>
Notes: <driver version, docker version, issues>
```

## Troubleshooting

- **GPU not visible in containers**
  - Reinstall/reconfigure NVIDIA Container Toolkit
  - Restart Docker: `sudo systemctl restart docker`
  - Re-test: `docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi`

- **MAX Serve health endpoint unavailable**
  - Check container status: `docker compose ps`
  - Inspect logs: `docker compose logs max-serve`

- **SSH denied**
  - Validate authorized keys and file permissions (`~/.ssh`, `authorized_keys`)
  - Confirm firewall allows inbound port 22 from approved IPs
