from unittest.mock import MagicMock, patch

import paramiko
import pytest

from src.clients.hetzner import HetznerClient, _detect_product, HETZNER_PLANS


def _make_df_output(total_bytes: int, used_bytes: int) -> bytes:
    """Build mock output for `df -B1 /`."""
    available = total_bytes - used_bytes
    pct = int(used_bytes / total_bytes * 100)
    line = f"overlay {total_bytes} {used_bytes} {available} {pct}% /"
    return f"Filesystem     1B-blocks  Used  Available Use% Mounted on\n{line}\n".encode()


def _patch_ssh(total_bytes: int, used_bytes: int):
    """Patch paramiko.SSHClient so exec_command returns mock df output."""
    mock_ssh = MagicMock()
    stdout = MagicMock()
    stdout.read.return_value = _make_df_output(total_bytes, used_bytes)
    mock_ssh.exec_command.return_value = (MagicMock(), stdout, MagicMock())
    return patch("paramiko.SSHClient", return_value=mock_ssh), mock_ssh


@pytest.fixture
def client():
    return HetznerClient(
        host="u123.your-storagebox.de",
        username="u123",
        password="secret",
        port=23,
    )


# ── _detect_product unit tests ────────────────────────────────────────────────

def test_detect_product_bx31():
    assert _detect_product(10_000_000_000_000) == "BX31"


def test_detect_product_bx11():
    assert _detect_product(1_000_000_000_000) == "BX11"


def test_detect_product_bx21():
    assert _detect_product(5_000_000_000_000) == "BX21"


def test_detect_product_bx41():
    assert _detect_product(20_000_000_000_000) == "BX41"


def test_detect_product_with_filesystem_overhead():
    # Filesystem may report slightly less than advertised
    assert _detect_product(9_900_000_000_000) == "BX31"


def test_detect_product_unknown_large_returns_last_plan():
    assert _detect_product(100_000_000_000_000) == HETZNER_PLANS[-1][0]


# ── HetznerClient SSH tests ───────────────────────────────────────────────────

async def test_get_storageboxes_returns_single_box(client):
    total = 10_000_000_000_000
    used = 7_200_000_000_000
    ssh_patch, mock_ssh = _patch_ssh(total, used)
    with ssh_patch:
        boxes = await client.get_storageboxes()

    assert len(boxes) == 1
    box = boxes[0]
    assert box.login == "u123"
    assert box.disk_quota == total
    assert box.disk_usage == used


async def test_get_storageboxes_detects_bx31(client):
    ssh_patch, _ = _patch_ssh(10_000_000_000_000, 2_800_000_000_000)
    with ssh_patch:
        boxes = await client.get_storageboxes()

    assert boxes[0].product == "BX31"


async def test_get_storageboxes_product_override():
    c = HetznerClient(
        host="u123.your-storagebox.de",
        username="u123",
        password="s",
        product="BX41",
    )
    ssh_patch, _ = _patch_ssh(20_000_000_000_000, 5_000_000_000_000)
    with ssh_patch:
        boxes = await c.get_storageboxes()

    assert boxes[0].product == "BX41"


async def test_get_storageboxes_used_equals_df_used(client):
    total = 10_000_000_000_000
    used = 2_800_000_000_000
    ssh_patch, _ = _patch_ssh(total, used)
    with ssh_patch:
        boxes = await client.get_storageboxes()

    assert boxes[0].disk_usage == used


async def test_get_storagebox_returns_first_box(client):
    ssh_patch, _ = _patch_ssh(10_000_000_000_000, 5_000_000_000_000)
    with ssh_patch:
        box = await client.get_storagebox(0)

    assert box is not None
    assert box.login == "u123"


async def test_get_storageboxes_auth_error_propagates(client):
    with patch("paramiko.SSHClient") as mock_ssh_cls:
        mock_ssh = MagicMock()
        mock_ssh_cls.return_value = mock_ssh
        mock_ssh.connect.side_effect = paramiko.AuthenticationException("bad credentials")

        with pytest.raises(paramiko.AuthenticationException):
            await client.get_storageboxes()


async def test_get_storageboxes_uses_correct_host_and_port(client):
    ssh_patch, mock_ssh = _patch_ssh(10_000_000_000_000, 5_000_000_000_000)
    with ssh_patch:
        await client.get_storageboxes()

    mock_ssh.connect.assert_called_once_with(
        "u123.your-storagebox.de",
        port=23,
        username="u123",
        password="secret",
        timeout=30,
    )


async def test_get_storageboxes_ssh_closed_on_success(client):
    ssh_patch, mock_ssh = _patch_ssh(10_000_000_000_000, 5_000_000_000_000)
    with ssh_patch:
        await client.get_storageboxes()

    mock_ssh.close.assert_called_once()
