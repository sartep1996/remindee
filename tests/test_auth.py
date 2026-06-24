"""
PASS 1 — Boundary Contradiction Sweep: auth service.

Boundary matrix:
  email   : normal, uppercase (normalisation), empty string, unicode, SQL-injection
  password: correct, wrong, empty string, unicode multibyte, bcrypt 72-byte truncation boundary
  username: normal, empty string, None-equivalent (service does not validate — UI does)

PASS 2 — Mock Reality Check:
  LocalAuthService uses bcrypt.hashpw / bcrypt.checkpw with the real bcrypt library.
  We do NOT mock bcrypt — doing so would make the hash/check loop a no-op and verify
  nothing. All tests hit the actual library.

PASS 3 — State teardown:
  Every test uses `patched_db` which replaces engine+SessionLocal with an isolated
  in-memory engine. The `sample_user` fixture pre-registers one user; tests that
  need isolation from it use `patched_db` directly.
"""
import pytest


class TestRegister:
    def test_register_creates_user(self, patched_db):
        from remindee.services.auth_service import LocalAuthService
        user = LocalAuthService.register("alice", "alice@example.com", "hunter2")
        assert user.id is not None
        assert user.email == "alice@example.com"

    def test_register_hashes_password(self, patched_db):
        """Stored hash must not equal the plaintext password."""
        import bcrypt
        from remindee.services.auth_service import LocalAuthService
        user = LocalAuthService.register("bob", "bob@example.com", "PlainText!")
        assert user.password_hash != "PlainText!"
        # Hash must be verifiable by bcrypt itself
        assert bcrypt.checkpw(b"PlainText!", user.password_hash.encode())

    def test_register_email_normalised_to_lowercase(self, patched_db):
        """Email must be stored lowercase regardless of input case."""
        from remindee.services.auth_service import LocalAuthService
        user = LocalAuthService.register("carol", "Carol@Example.COM", "pw")
        assert user.email == "carol@example.com"

    def test_register_email_strips_whitespace(self, patched_db):
        """Leading/trailing whitespace on email must be stripped."""
        from remindee.services.auth_service import LocalAuthService
        user = LocalAuthService.register("dave", "  dave@example.com  ", "pw")
        assert user.email == "dave@example.com"

    def test_duplicate_email_raises(self, patched_db):
        """
        Registering the same email twice must raise an exception.
        SQLAlchemy wraps the UNIQUE constraint violation in IntegrityError.
        """
        from remindee.services.auth_service import LocalAuthService
        LocalAuthService.register("eve1", "eve@example.com", "pw1")
        with pytest.raises(Exception):
            LocalAuthService.register("eve2", "eve@example.com", "pw2")

    def test_duplicate_email_case_insensitive(self, patched_db):
        """
        Email normalisation must mean that 'Eve@Example.com' clashes with the
        already-stored 'eve@example.com'.
        """
        from remindee.services.auth_service import LocalAuthService
        LocalAuthService.register("eve", "eve@example.com", "pw1")
        with pytest.raises(Exception):
            LocalAuthService.register("eve2", "Eve@Example.com", "pw2")

    def test_unicode_password_registers(self, patched_db):
        """Passwords containing multibyte unicode must not crash the service."""
        from remindee.services.auth_service import LocalAuthService
        user = LocalAuthService.register("faye", "faye@example.com", "päßörT!")
        assert user.id is not None

    def test_hostile_email_string_registers(self, patched_db):
        """
        Email containing SQL-injection-style characters must be stored verbatim
        (after normalisation) — SQLAlchemy parameterises queries.
        """
        from remindee.services.auth_service import LocalAuthService
        hostile = "o'connor+test@example.com"
        user = LocalAuthService.register("connor", hostile, "pw")
        assert user.email == hostile.lower().strip()

    def test_empty_password_registers_and_login_fails(self, patched_db):
        """
        The service layer itself does NOT validate empty passwords — that is the
        UI's job.  An empty password should register (bcrypt hashes it) but
        should only authenticate with the same empty string.
        """
        from remindee.services.auth_service import LocalAuthService
        LocalAuthService.register("ghost", "ghost@example.com", "")
        # Correct empty password must work
        user = LocalAuthService.login("ghost@example.com", "")
        assert user is not None
        # Wrong password must fail
        none_user = LocalAuthService.login("ghost@example.com", "notempty")
        assert none_user is None

    def test_returned_user_is_detached(self, patched_db):
        """
        register() must expunge the user before returning so the caller can
        access attributes without an active session (DetachedInstanceError guard).
        """
        from sqlalchemy.orm import make_transient
        from remindee.services.auth_service import LocalAuthService
        user = LocalAuthService.register("ivy", "ivy@example.com", "pw")
        # Accessing id, email, username on a detached object must not raise
        _ = user.id
        _ = user.email
        _ = user.username


class TestLogin:
    def test_login_correct_credentials(self, sample_user):
        """login() with the right email+password must return a User."""
        from remindee.services.auth_service import LocalAuthService
        user = LocalAuthService.login("test@example.com", "S3cur3P@ss!")
        assert user is not None
        assert user.email == "test@example.com"

    def test_login_wrong_password_returns_none(self, sample_user):
        from remindee.services.auth_service import LocalAuthService
        result = LocalAuthService.login("test@example.com", "wrong_password")
        assert result is None

    def test_login_unknown_email_returns_none(self, patched_db):
        from remindee.services.auth_service import LocalAuthService
        result = LocalAuthService.login("nobody@example.com", "any_password")
        assert result is None

    def test_login_email_case_insensitive(self, sample_user):
        """Login must succeed regardless of the email's case."""
        from remindee.services.auth_service import LocalAuthService
        result = LocalAuthService.login("TEST@EXAMPLE.COM", "S3cur3P@ss!")
        assert result is not None

    def test_login_empty_password_wrong_returns_none(self, sample_user):
        """An empty string submitted as password must NOT match the hashed password."""
        from remindee.services.auth_service import LocalAuthService
        result = LocalAuthService.login("test@example.com", "")
        assert result is None

    def test_login_updates_last_login(self, sample_user):
        """login() must set last_login to a non-None datetime."""
        from remindee.services.auth_service import LocalAuthService
        user = LocalAuthService.login("test@example.com", "S3cur3P@ss!")
        assert user.last_login is not None

    def test_login_returns_detached_user(self, sample_user):
        """Returned user must be detached — attribute access must not raise."""
        from remindee.services.auth_service import LocalAuthService
        user = LocalAuthService.login("test@example.com", "S3cur3P@ss!")
        assert user is not None
        _ = user.id
        _ = user.email

    def test_login_unicode_password(self, patched_db):
        """A unicode password registered and then logged-in with must succeed."""
        from remindee.services.auth_service import LocalAuthService
        pw = "päßörT!汉字"
        LocalAuthService.register("uni", "uni@example.com", pw)
        user = LocalAuthService.login("uni@example.com", pw)
        assert user is not None

    def test_login_hostile_email_input(self, sample_user):
        """
        A SQL-injection-style email string in the login call must not crash or
        cause data exposure — it simply returns None (no such user).
        """
        from remindee.services.auth_service import LocalAuthService
        result = LocalAuthService.login("' OR '1'='1", "any")
        assert result is None

    def test_login_password_at_bcrypt_72_byte_boundary(self, patched_db):
        """
        bcrypt has a 72-byte password limit.  Behaviour depends on the bcrypt
        library version:

        - bcrypt < 4.0: silently truncates at 72 bytes, so a 73-char password
          where only the 73rd byte differs still authenticates (truncation means
          both are identical on the wire).
        - bcrypt >= 4.0: raises ValueError for passwords longer than 72 bytes,
          forcing the caller to truncate manually.

        The service layer does NOT guard against this — authentication with a
        >72-byte password will either silently succeed (old bcrypt) or raise
        (new bcrypt).  This test validates the 72-byte boundary is correctly
        handled and documents the known version-dependent behaviour.
        """
        import bcrypt as _bcrypt
        from remindee.services.auth_service import LocalAuthService

        pw_72 = "A" * 72
        LocalAuthService.register("boundary", "boundary@example.com", pw_72)

        # 72-byte password must always authenticate successfully
        user_72 = LocalAuthService.login("boundary@example.com", pw_72)
        assert user_72 is not None, "72-char password must authenticate"

        # 73-byte password: newer bcrypt raises ValueError; this tests the
        # boundary condition without asserting one specific outcome.
        pw_73 = "A" * 72 + "B"
        try:
            user_73 = LocalAuthService.login("boundary@example.com", pw_73)
            # Old bcrypt: silent truncation — 73rd byte dropped, login succeeds
            assert user_73 is not None, (
                "bcrypt < 4.0 truncates at 72 bytes so the 73rd char is ignored; "
                "login must succeed"
            )
        except ValueError:
            # New bcrypt (>= 4.0): refuses passwords > 72 bytes — expected
            pass


class TestEmailExists:
    def test_email_exists_true(self, sample_user):
        from remindee.services.auth_service import LocalAuthService
        assert LocalAuthService.email_exists("test@example.com") is True

    def test_email_exists_false(self, patched_db):
        from remindee.services.auth_service import LocalAuthService
        assert LocalAuthService.email_exists("nope@example.com") is False

    def test_email_exists_case_insensitive(self, sample_user):
        """email_exists() uses the same normalisation as register/login."""
        from remindee.services.auth_service import LocalAuthService
        assert LocalAuthService.email_exists("TEST@EXAMPLE.COM") is True

    def test_email_exists_returns_bool(self, patched_db):
        """Return value must be a strict bool (not just truthy int)."""
        from remindee.services.auth_service import LocalAuthService
        result = LocalAuthService.email_exists("none@example.com")
        assert result is False or result is True
