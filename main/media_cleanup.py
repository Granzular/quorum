"""Explicit file lifecycle helpers using Django storage and commit callbacks.

Callbacks are best effort: a process failure between commit and callback
execution can leave an orphan. Database rollback cannot undo a new upload.
"""

from hashlib import sha256
import logging

from django.apps import apps
from django.db import models, router, transaction
from django.db.models.deletion import Collector


logger = logging.getLogger(__name__)


def _file_fields(model):
    return [field for field in model._meta.concrete_fields if isinstance(field, models.FileField)]


def _stored_files(objects):
    """Snapshot storage/name pairs rather than retaining mutable FieldFiles."""
    files = []
    for obj in objects:
        for field in _file_fields(type(obj)):
            file = getattr(obj, field.attname)
            if file:
                files.append((file.storage, file.name))
    return files


def _is_referenced(storage, name, using):
    # Check every existing file field, including references outside the feature
    # being changed. Different storage instances may represent different assets.
    for model in apps.get_models():
        for field in _file_fields(model):
            if field.storage is storage and model._base_manager.using(using).filter(
                **{field.attname: name}
            ).exists():
                return True
    return False


def schedule_file_cleanup(files, *, operation, using):
    """Delete unreferenced stored names after commit; log failures safely.

    Each operation schedules a given storage/name pair once. Storage.delete()
    normally returns None; False is also handled because the Cloudinary adapter
    uses it to report an unsuccessful destruction response.
    """
    unique_files = {(id(storage), name): (storage, name) for storage, name in files if name}
    if not unique_files:
        return

    def cleanup():
        for storage, name in unique_files.values():
            # Filenames may contain personal information. A fingerprint permits
            # correlation without logging names, URLs, or provider credentials.
            identifier = sha256(name.encode()).hexdigest()[:16]
            if (
                name.startswith(('/', '\\')) or ':' in name or '?' in name or '#' in name
                or '\x00' in name or '..' in name.replace('\\', '/').split('/')
            ):
                logger.error(
                    'Media cleanup rejected an invalid reference (operation=%s, asset=%s)',
                    operation, identifier, extra={'event': 'media.cleanup_invalid_reference'},
                )
                continue
            try:
                if not _is_referenced(storage, name, using):
                    if storage.delete(name) is False:
                        raise RuntimeError('Storage did not confirm file deletion.')
            except Exception:
                logger.exception(
                    'Media cleanup failed (operation=%s, storage=%s, asset=%s)',
                    operation, storage.__class__.__name__, identifier,
                    extra={'event': 'media.cleanup_failed'},
                )

    transaction.on_commit(cleanup, using=using)


def save_with_file_cleanup(instance, save, **kwargs):
    """Persist a model save and schedule cleanup only for changed file fields."""
    using = kwargs.get('using') or router.db_for_write(type(instance), instance=instance)
    update_fields = kwargs.get('update_fields')
    fields = [
        field for field in _file_fields(type(instance))
        if update_fields is None or field.name in update_fields or field.attname in update_fields
    ]
    if not fields:
        return save(**kwargs)

    with transaction.atomic(using=using):
        previous = None
        if instance.pk is not None:
            previous = type(instance)._base_manager.using(using).select_for_update().filter(
                pk=instance.pk
            ).only(*(field.attname for field in fields)).first()
        old_files = {
            field.attname: (getattr(previous, field.attname).storage, getattr(previous, field.attname).name)
            for field in fields if previous is not None and getattr(previous, field.attname)
        }
        result = save(**kwargs)
        changed = {'replace': [], 'clear': []}
        for field in fields:
            old = old_files.get(field.attname)
            current = getattr(instance, field.attname)
            if old and old[1] != current.name:
                changed['replace' if current else 'clear'].append(old)
        for operation, files in changed.items():
            schedule_file_cleanup(files, operation=operation, using=using)
        return result


def delete_with_file_cleanup(target, delete, *, using, **kwargs):
    """Snapshot files on a record/queryset and its cascades before deletion.

    Django's collector also exposes fast-delete querysets, whose models would
    otherwise bypass Model.delete(). The actual deletion remains Django's
    existing delete operation, preserving its return value and signal behavior.
    """
    with transaction.atomic(using=using):
        collector = Collector(using=using)
        collector.collect(
            target if isinstance(target, models.QuerySet) else [target],
            keep_parents=kwargs.get('keep_parents', False),
        )
        files = _stored_files(obj for objects in collector.data.values() for obj in objects)
        for queryset in collector.fast_deletes:
            if _file_fields(queryset.model):
                files.extend(_stored_files(queryset))
        result = delete(**kwargs) if isinstance(target, models.QuerySet) else delete(using=using, **kwargs)
        schedule_file_cleanup(files, operation='delete', using=using)
        return result


class FileCleanupQuerySet(models.QuerySet):
    """Explicitly cover bulk deletions, including admin actions and cascades."""

    def delete(self):
        self._for_write = True
        return delete_with_file_cleanup(self, super().delete, using=self.db)

    delete.alters_data = True
    delete.queryset_only = True
