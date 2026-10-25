"""Cloudinary storage backends and registry helpers for project media."""

import os

import cloudinary.uploader
from cloudinary_storage.storage import (
    MediaCloudinaryStorage,
    RawMediaCloudinaryStorage,
)

from django.core.files.storage import storages


class _DynamicFolderUploadMixin:
    """Place assets in Media Library folders without prefixing public IDs."""

    def _upload(self, name, content):
        options = {
            'use_filename': True,
            'resource_type': self._get_resource_type(name),
            'tags': self.TAG,
        }
        asset_folder = os.path.dirname(name)
        if asset_folder:
            options.update(
                asset_folder=asset_folder,
                use_asset_folder_as_public_id_prefix=False,
            )
        return cloudinary.uploader.upload(content, **options)


class DynamicFolderMediaCloudinaryStorage(
    _DynamicFolderUploadMixin, MediaCloudinaryStorage,
):
    """Image storage using Cloudinary Dynamic Folder Mode semantics."""


class DynamicFolderRawMediaCloudinaryStorage(
    _DynamicFolderUploadMixin, RawMediaCloudinaryStorage,
):
    """Raw-file storage using Cloudinary Dynamic Folder Mode semantics."""


def file_storage():
    """Generic FileFields use raw storage; ImageFields use the default backend."""
    return storages['files']
