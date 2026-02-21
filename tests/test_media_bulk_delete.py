from types import SimpleNamespace

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from rewrz.api import media as media_api
from rewrz.models import Base
from rewrz.models.media import Media as MediaModel
from rewrz.schemas import UserCreate
from rewrz.crud import user as crud_user


def test_bulk_delete_media_uses_filepath_snapshot_and_no_object_deleted_error(tmp_path, monkeypatch):
    db_path = tmp_path / "media_bulk_delete_test.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        # 绕过 CSRF 校验，聚焦回归点：批量删除后文件删除阶段不应访问已删除 ORM 对象。
        monkeypatch.setattr(media_api, "verify_csrf_token", lambda request, token: None)

        owner = crud_user.create_user(
            db,
            UserCreate(username="owner", email="owner@example.com", password="password123"),
        )
        other = crud_user.create_user(
            db,
            UserCreate(username="other", email="other@example.com", password="password123"),
        )

        owner_media = MediaModel(
            filename="a.jpg",
            filepath=str(tmp_path / "a.jpg"),
            file_type="image",
            mime_type="image/jpeg",
            uploaded_by_id=owner.id,
        )
        other_media = MediaModel(
            filename="b.jpg",
            filepath=str(tmp_path / "b.jpg"),
            file_type="image",
            mime_type="image/jpeg",
            uploaded_by_id=other.id,
        )
        db.add_all([owner_media, other_media])
        db.commit()
        db.refresh(owner_media)
        db.refresh(other_media)
        owner_media_id = int(owner_media.id)
        other_media_id = int(other_media.id)

        deleted_filepaths = []
        monkeypatch.setattr(
            media_api,
            "_delete_media_files_by_filepath",
            lambda filepath: deleted_filepaths.append(filepath),
        )

        result = media_api.bulk_delete_media_items(
            request=SimpleNamespace(),
            payload=media_api.MediaBulkDeleteRequest(media_ids=[owner_media_id, other_media_id, 999999]),
            db=db,
            current_user=owner,
            csrf_token="test-token",
        )

        assert result["deleted_count"] == 1
        assert result["deleted_ids"] == [owner_media_id]
        assert len(result["skipped"]) == 2
        assert str(tmp_path / "a.jpg") in deleted_filepaths
        assert str(tmp_path / "b.jpg") not in deleted_filepaths

        remaining_ids = set(db.execute(select(MediaModel.id)).scalars().all())
        assert owner_media_id not in remaining_ids
        assert other_media_id in remaining_ids
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
