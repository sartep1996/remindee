from __future__ import annotations

import re

from sqlalchemy import nullslast, or_

from remindee.models.note import Note
from remindee.models.note_folder import NoteFolder
from remindee.models.reminder import Reminder
from remindee.utils.database import get_session


def _plain_text(content: str) -> str:
    """Return plain text from either HTML (rich notes) or legacy Markdown."""
    text = (content or "").strip()
    if text.startswith("<"):
        # Remove <style>…</style> blocks first (QTextEdit.toHtml embeds CSS like
        # "p, li { white-space: pre-wrap; }" that leaks into plain-text extraction)
        text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)
        text = (text.replace("&amp;", "&").replace("&lt;", "<")
                    .replace("&gt;", ">").replace("&nbsp;", " ").replace("&#160;", " "))
        return " ".join(text.split())
    # Legacy Markdown
    text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    text = re.sub(r"`[^`]*`", "", text)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"^#{1,6}\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"(\*{1,3}|_{1,3})(.*?)\1", r"\2", text)
    text = re.sub(r"^[-*_]{3,}\s*$", "", text, flags=re.MULTILINE)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


class NoteService:
    # ── Notes ────────────────────────────────────────────────────────────────

    @staticmethod
    def _note_order():
        """Pinned notes first, then newest-updated first; nulls last."""
        return (
            Note.is_pinned.desc(),
            nullslast(Note.updated_at.desc()),
        )

    def get_all_notes(self, user_id: int) -> list[Note]:
        with get_session() as session:
            notes = (
                session.query(Note)
                .filter(Note.user_id == user_id)
                .order_by(*self._note_order())
                .all()
            )
            for note in notes:
                session.expunge(note)
            return notes

    def get_notes_in_folder(self, user_id: int, folder_id: int) -> list[Note]:
        with get_session() as session:
            notes = (
                session.query(Note)
                .filter(Note.user_id == user_id, Note.folder_id == folder_id)
                .order_by(*self._note_order())
                .all()
            )
            for note in notes:
                session.expunge(note)
            return notes

    def get_pinned_notes(self, user_id: int) -> list[Note]:
        with get_session() as session:
            notes = (
                session.query(Note)
                .filter(Note.user_id == user_id, Note.is_pinned.is_(True))
                .order_by(nullslast(Note.updated_at.desc()))
                .all()
            )
            for note in notes:
                session.expunge(note)
            return notes

    def create_note(
        self,
        user_id: int,
        title: str = "",
        body_md: str = "",
        folder_id: int | None = None,
        color_label: str | None = None,
        attachments: str | None = None,
    ) -> Note:
        with get_session() as session:
            note = Note(
                user_id=user_id,
                title=title,
                body_md=body_md,
                folder_id=folder_id,
                color_label=color_label,
                attachments=attachments,
            )
            session.add(note)
            session.flush()
            session.expunge(note)
            return note

    def update_note(self, note_id: int, **kwargs) -> Note:
        with get_session() as session:
            note = session.query(Note).filter(Note.id == note_id).one()
            for key, value in kwargs.items():
                setattr(note, key, value)
            session.flush()
            session.expunge(note)
            return note

    def delete_note(self, note_id: int) -> None:
        with get_session() as session:
            note = session.query(Note).filter(Note.id == note_id).one()
            session.delete(note)

    def toggle_pin(self, note_id: int) -> bool:
        with get_session() as session:
            note = session.query(Note).filter(Note.id == note_id).one()
            note.is_pinned = not note.is_pinned
            new_value = note.is_pinned
            session.flush()
            return new_value

    # ── Folders ──────────────────────────────────────────────────────────────

    def get_folders(self, user_id: int) -> list[NoteFolder]:
        with get_session() as session:
            folders = (
                session.query(NoteFolder)
                .filter(NoteFolder.user_id == user_id)
                .order_by(NoteFolder.created_at.desc())
                .all()
            )
            for folder in folders:
                session.expunge(folder)
            return folders

    def create_folder(self, user_id: int, name: str) -> NoteFolder:
        with get_session() as session:
            folder = NoteFolder(user_id=user_id, name=name)
            session.add(folder)
            session.flush()
            session.expunge(folder)
            return folder

    def rename_folder(self, folder_id: int, name: str) -> NoteFolder:
        with get_session() as session:
            folder = (
                session.query(NoteFolder)
                .filter(NoteFolder.id == folder_id)
                .one()
            )
            folder.name = name
            session.flush()
            session.expunge(folder)
            return folder

    def delete_folder(self, folder_id: int) -> None:
        with get_session() as session:
            folder = (
                session.query(NoteFolder)
                .filter(NoteFolder.id == folder_id)
                .one()
            )
            session.delete(folder)

    # ── Search ───────────────────────────────────────────────────────────────

    def search_notes(self, user_id: int, query: str) -> list[Note]:
        with get_session() as session:
            pattern = f"%{query}%"
            notes = (
                session.query(Note)
                .filter(
                    Note.user_id == user_id,
                    or_(
                        Note.title.ilike(pattern),
                        Note.body_md.ilike(pattern),
                    ),
                )
                .order_by(*self._note_order())
                .all()
            )
            for note in notes:
                session.expunge(note)
            return notes

    # ── Conversion ───────────────────────────────────────────────────────────

    def reminder_to_note(self, reminder: Reminder, user_id: int) -> Note:
        return self.create_note(
            user_id=user_id,
            title=reminder.name,
            body_md=reminder.details or "",
        )

    def note_to_reminder_kwargs(self, note: Note) -> dict:
        return {
            "prefill_name": note.title or "Untitled",
            "prefill_details": _plain_text(note.body_md or ""),
        }
