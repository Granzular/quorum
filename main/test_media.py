"""Storage and explicit file lifecycle regressions; no real provider operations."""

from hashlib import sha256
from io import StringIO
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

from django.apps import apps
from django.conf import settings
from django.db import models
from django.core.files.storage import InMemoryStorage
from django.db import transaction
from django.test import SimpleTestCase, TestCase, TransactionTestCase
from rest_framework.test import APIClient, APIRequestFactory

from accounts.models import CustomUser, Profile
from accounts.serializers import ProfileUpdateSerializer
from accounts.tests.test_api import AVATAR, CURRENT, image_upload
from community.models import Content
from community.serializers import PostSerializer
from community.views import PostViewSet
from library.models import Resource
from main.media_cleanup import schedule_file_cleanup
from mysite.logging import JSONFormatter


class StorageConfigurationTests(SimpleTestCase):
    def run_configuration(self, credentials, code):
        env = {key: value for key, value in os.environ.items() if not key.startswith('CLOUDINARY_')}
        env.update(
            DJANGO_SETTINGS_MODULE='mysite.settings',
            SECRET_KEY='media-test-secret-key-at-least-32-characters',
            **credentials,
        )
        # Test process configuration independently of the developer's .env.
        setup = 'import dotenv; dotenv.load_dotenv = lambda *a, **kw: None; import django; django.setup(); '
        result = subprocess.run(
            [sys.executable, '-c', setup + code], env=env,
            cwd=Path(__file__).resolve().parent.parent,
            text=True, capture_output=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_configuration_uses_cloudinary_url_and_preserves_static_storage(self):
        self.run_configuration(
            {'CLOUDINARY_URL': 'cloudinary://test-key:test-secret@media-tests'},
            'from django.core.files.storage import storages; import cloudinary; '
            'from django.conf import settings; '
            'assert cloudinary.config().cloud_name == "media-tests"; '
            'assert cloudinary.config().api_key == "test-key"; '
            'assert cloudinary.config().api_secret == "test-secret"; '
            'assert storages["default"].RESOURCE_TYPE == "image"; '
            'assert storages["files"].RESOURCE_TYPE == "raw"; '
            'assert type(storages["default"]).__name__ == "DynamicFolderMediaCloudinaryStorage"; '
            'assert type(storages["files"]).__name__ == "DynamicFolderRawMediaCloudinaryStorage"; '
            'assert type(storages["staticfiles"]).__module__ == "whitenoise.storage"; '
            'assert settings.CLOUDINARY_STORAGE["PREFIX"] == ""; '
            'assert storages["default"].url("quorum/accounts/avatar").startswith("https://"); '
            'from django.core.management import get_commands; '
            'assert get_commands()["collectstatic"] == "django.contrib.staticfiles"',
        )

    def test_configuration_uses_individual_environment_credentials(self):
        self.run_configuration(
            {
                'CLOUDINARY_CLOUD_NAME': 'media-tests',
                'CLOUDINARY_API_KEY': 'test-key',
                'CLOUDINARY_API_SECRET': 'test-secret',
            },
            'from django.core.files.storage import storages; import cloudinary; '
            'assert storages["default"].RESOURCE_TYPE == "image"; '
            'assert cloudinary.config().cloud_name == "media-tests"; '
            'assert cloudinary.config().api_key == "test-key"; '
            'assert cloudinary.config().api_secret == "test-secret"',
        )

    def test_feature_folders_and_adapter_upload_options(self):
        self.run_configuration(
            {'CLOUDINARY_URL': 'cloudinary://test-key:test-secret@media-tests'},
            'from unittest.mock import patch; '
            'from django.core.files.base import ContentFile; '
            'from accounts.models import Profile; from community.models import Content; '
            'from library.models import Resource; '
            'avatar = Profile._meta.get_field("avatar"); media = Content._meta.get_field("media"); '
            'assert avatar.generate_filename(Profile(), "avatar.png").replace(chr(92), "/") == "quorum/accounts/avatars/avatar.png"; '
            'assert media.generate_filename(Content(), "post.txt").replace(chr(92), "/") == "quorum/community/posts/post.txt"; '
            'assert Resource._meta.get_field("file").upload_to == "quorum/library/resources/"; '
            'upload = patch("cloudinary.uploader.upload"); mock = upload.start(); '
            'mock.side_effect = [{"public_id":"avatar_unique1"}, '
            '{"public_id":"avatar_unique2"}, '
            '{"public_id":"post_unique.txt"}]; '
            'first = avatar.storage.save(avatar.generate_filename(Profile(), "avatar.png"), ContentFile(b"image")); '
            'second = avatar.storage.save(avatar.generate_filename(Profile(), "avatar.png"), ContentFile(b"image")); '
            'assert first != second; '
            'assert mock.call_args.kwargs["asset_folder"] == "quorum/accounts/avatars"; '
            'assert mock.call_args.kwargs["use_asset_folder_as_public_id_prefix"] is False; '
            'assert "folder" not in mock.call_args.kwargs; '
            'assert mock.call_args.kwargs["use_filename"] is True; '
            'assert "public_id" not in mock.call_args.kwargs; '
            'assert "overwrite" not in mock.call_args.kwargs; '
            'assert media.storage.save(media.generate_filename(Content(), "post.txt"), ContentFile(b"file")).endswith(".txt"); '
            'assert mock.call_args.kwargs["asset_folder"] == "quorum/community/posts"; '
            'assert mock.call_args.kwargs["use_asset_folder_as_public_id_prefix"] is False; '
            'assert "folder" not in mock.call_args.kwargs; '
            'assert mock.call_args.kwargs["resource_type"] == "raw"; upload.stop()',
        )

    def test_adapter_deletes_exact_stored_ids_with_the_correct_resource_type(self):
        self.run_configuration(
            {'CLOUDINARY_URL': 'cloudinary://test-key:test-secret@media-tests'},
            'from unittest.mock import patch; from django.core.files.storage import storages; '
            'destroy = patch("cloudinary.uploader.destroy", return_value={"result":"ok"}); '
            'mock = destroy.start(); '
            'assert storages["default"].delete("quorum/accounts/avatar_unique") is True; '
            'assert mock.call_args.args == ("quorum/accounts/avatar_unique",); '
            'assert mock.call_args.kwargs == {"invalidate":True, "resource_type":"image"}; '
            'assert storages["files"].delete("quorum/community/post_unique.txt") is True; '
            'assert mock.call_args.args == ("quorum/community/post_unique.txt",); '
            'assert mock.call_args.kwargs == {"invalidate":True, "resource_type":"raw"}; destroy.stop()',
        )

    def test_central_folder_convention_covers_existing_fields_and_planned_categories(self):
        expected = {
            'accounts': {'avatars': 'quorum/accounts/avatars/'},
            'community': {'posts': 'quorum/community/posts/'},
            'library': {
                'covers': 'quorum/library/covers/',
                'resources': 'quorum/library/resources/',
            },
        }
        self.assertEqual(settings.MEDIA_UPLOAD_FOLDERS, expected)
        folders = {folder for feature in expected.values() for folder in feature.values()}
        for model in apps.get_models():
            if model._meta.app_label not in {'accounts', 'community', 'library'}:
                continue
            for field in model._meta.concrete_fields:
                if isinstance(field, models.FileField):
                    with self.subTest(model=model.__name__, field=field.name):
                        self.assertIn(field.upload_to, folders)
                        self.assertRegex(field.upload_to, r'\Aquorum/[a-z]+/[a-z]+/\Z')
        self.assertEqual(Profile._meta.get_field('avatar').upload_to, expected['accounts']['avatars'])

    def test_avatar_adapter_round_trip_uses_returned_identity_without_folder_prefix(self):
        self.run_configuration(
            {'CLOUDINARY_URL': 'cloudinary://test-key:test-secret@media-tests'},
            'from unittest.mock import patch; from django.core.files.base import ContentFile; '
            'from accounts.models import Profile; '
            'upload = patch("cloudinary.uploader.upload", return_value={"public_id":"opaque-avatar-unique"}); '
            'mock_upload = upload.start(); '
            'profile = Profile(); profile.avatar.save("avatar.png", ContentFile(b"image"), save=False); '
            'assert mock_upload.call_args.kwargs["asset_folder"] == "quorum/accounts/avatars"; '
            'assert mock_upload.call_args.kwargs["use_asset_folder_as_public_id_prefix"] is False; '
            'assert "folder" not in mock_upload.call_args.kwargs; '
            'assert profile.avatar.name == "opaque-avatar-unique"; '
            'resource = patch("cloudinary.CloudinaryResource"); mock_resource = resource.start(); '
            'url = profile.avatar.url; '
            'assert mock_resource.call_args.args == ("opaque-avatar-unique",); '
            'destroy = patch("cloudinary.uploader.destroy", return_value={"result":"ok"}); '
            'mock_destroy = destroy.start(); profile.avatar.storage.delete(profile.avatar.name); '
            'assert mock_destroy.call_args.args == ("opaque-avatar-unique",); '
            'destroy.stop(); resource.stop(); upload.stop()',
        )

    def test_old_avatar_identifiers_are_not_rebuilt_from_the_new_folder(self):
        self.run_configuration(
            {'CLOUDINARY_URL': 'cloudinary://test-key:test-secret@media-tests'},
            'from unittest.mock import patch; from accounts.models import Profile; '
            'resource = patch("cloudinary.CloudinaryResource"); mock_resource = resource.start(); '
            'legacy = Profile(avatar="accounts/existing.png"); url = legacy.avatar.url; '
            'assert legacy.avatar.name == "accounts/existing.png"; '
            'assert mock_resource.call_args.args == ("accounts/existing.png",); '
            'opaque = Profile(avatar="existing-opaque-id"); url = opaque.avatar.url; '
            'assert mock_resource.call_args.args == ("existing-opaque-id",); resource.stop()',
        )


class MediaFixtures:
    def setUp(self):
        super().setUp()
        self.storage = InMemoryStorage()
        for model, name in ((Profile, 'avatar'), (Content, 'media'), (Resource, 'file')):
            storage_patch = patch.object(model._meta.get_field(name), 'storage', self.storage)
            storage_patch.start()
            self.addCleanup(storage_patch.stop)
        self.owner = CustomUser.objects.create_user(username='media-owner')
        self.profile = Profile.objects.create(
            user=self.owner, profile_type='staff', job_title='Lecturer',
            avatar='quorum/accounts/old-image',
        )
        self.client = APIClient()
        self.client.force_authenticate(self.owner)

    def post(self, **kwargs):
        return Content.objects.create(
            author=self.owner, type='post', title='Post',
            media='quorum/community/old-file', **kwargs,
        )


class MediaLifecycleTests(MediaFixtures, TestCase):
    def test_replacement_upload_saves_new_reference_before_cleanup(self):
        self.profile.avatar = image_upload()
        with patch.object(self.storage, 'delete') as delete:
            with self.captureOnCommitCallbacks(execute=True) as callbacks:
                self.profile.save()
                stored = Profile.objects.get(pk=self.profile.pk).avatar.name
                self.assertTrue(stored.startswith('quorum/accounts/avatars/'))
                self.assertNotEqual(stored, 'quorum/accounts/old-image')
                self.assertTrue(self.storage.exists(stored))
                delete.assert_not_called()
            self.assertEqual(len(callbacks), 1)
            delete.assert_called_once_with('quorum/accounts/old-image')

    def test_database_stores_the_provider_returned_identity_without_reconstruction(self):
        self.profile.avatar = image_upload()
        with patch.object(self.storage, 'save', return_value='opaque-avatar-unique'):
            with patch.object(self.storage, 'delete') as delete:
                with self.captureOnCommitCallbacks(execute=True):
                    self.profile.save()
                    self.profile.refresh_from_db()
                    self.assertEqual(self.profile.avatar.name, 'opaque-avatar-unique')
                delete.assert_called_once_with('quorum/accounts/old-image')

    def test_existing_avatar_references_survive_updates_under_the_new_convention(self):
        for name in ('accounts/existing.png', 'quorum/accounts/old-image', 'existing-opaque-id'):
            with self.subTest(name=name):
                Profile.objects.filter(pk=self.profile.pk).update(avatar=name)
                self.profile.refresh_from_db()
                with self.captureOnCommitCallbacks(execute=True) as callbacks:
                    self.profile.bio = 'Updated biography'
                    self.profile.save()
                self.profile.refresh_from_db()
                self.assertEqual(self.profile.avatar.name, name)
                self.assertEqual(callbacks, [])

    def test_rollback_discards_replacement_cleanup(self):
        with patch.object(self.storage, 'delete') as delete:
            with self.captureOnCommitCallbacks(execute=True) as callbacks:
                with self.assertRaises(RuntimeError):
                    with transaction.atomic():
                        self.profile.avatar = image_upload()
                        self.profile.save()
                        raise RuntimeError('Roll back')
            self.profile.refresh_from_db()
            self.assertEqual(self.profile.avatar.name, 'quorum/accounts/old-image')
            self.assertEqual(callbacks, [])
            delete.assert_not_called()

    def test_unrelated_update_and_unchanged_name_do_not_schedule_cleanup(self):
        for attrs in ({'bio': 'New biography'}, {'avatar': 'quorum/accounts/old-image'}):
            with self.subTest(attrs=attrs):
                with self.captureOnCommitCallbacks(execute=True) as callbacks:
                    for field, value in attrs.items():
                        setattr(self.profile, field, value)
                    self.profile.save()
                self.assertEqual(callbacks, [])

    def test_update_fields_does_not_clean_up_unsaved_file_change(self):
        self.profile.avatar = None
        self.profile.bio = 'New biography'
        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            self.profile.save(update_fields=['bio'])
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.avatar.name, 'quorum/accounts/old-image')
        self.assertEqual(callbacks, [])

    def test_empty_file_fields_do_not_schedule_cleanup(self):
        self.profile.avatar = None
        self.profile.save()
        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            self.profile.bio = 'New biography'
            self.profile.save()
        self.assertEqual(callbacks, [])

    def test_clearing_via_nested_profile_api_preserves_response_contract(self):
        with patch.object(self.storage, 'delete') as delete:
            with self.captureOnCommitCallbacks(execute=True) as callbacks:
                response = self.client.patch(
                    CURRENT + f'{self.owner.pk}/', {'profile': {'avatar': None}}, format='json',
                )
                self.assertEqual(response.status_code, 200, response.data)
                self.assertIsNone(response.data['profile']['avatar'])
                self.profile.refresh_from_db()
                self.assertFalse(self.profile.avatar)
                delete.assert_not_called()
            self.assertEqual(len(callbacks), 1)
            delete.assert_called_once_with('quorum/accounts/old-image')

    def test_avatar_endpoint_replacement_preserves_response_contract(self):
        with patch.object(self.storage, 'delete') as delete:
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.put(AVATAR, {'avatar': image_upload()}, format='multipart')
                self.assertEqual(response.status_code, 200, response.data)
                self.assertEqual(response.data['status'], 'success')
                self.assertTrue(response.data['data']['avatar'])
                delete.assert_not_called()
            delete.assert_called_once_with('quorum/accounts/old-image')

    def test_serializer_upload_failure_preserves_old_database_reference(self):
        serializer = ProfileUpdateSerializer(self.profile, data={'avatar': image_upload()}, partial=True)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        with patch.object(self.storage, 'save', side_effect=RuntimeError('Upload failed')):
            with self.captureOnCommitCallbacks(execute=True) as callbacks:
                with self.assertRaises(RuntimeError):
                    serializer.save()
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.avatar.name, 'quorum/accounts/old-image')
        self.assertEqual(callbacks, [])

    def test_content_and_library_replacement_and_clear(self):
        post = self.post()
        resource = Resource.objects.create(name='Resource', file='resources/old-file')
        for obj, field in ((post, 'media'), (resource, 'file')):
            for value in (image_upload(), None):
                with self.subTest(model=type(obj).__name__, clear=value is None):
                    old_name = getattr(obj, field).name
                    with patch.object(self.storage, 'delete') as delete:
                        with self.captureOnCommitCallbacks(execute=True) as callbacks:
                            setattr(obj, field, value)
                            obj.save()
                            obj.refresh_from_db()
                            self.assertNotEqual(getattr(obj, field).name, old_name)
                            delete.assert_not_called()
                        self.assertEqual(len(callbacks), 1)
                        delete.assert_called_once_with(old_name)

    def test_post_serializer_clearing_media_uses_model_lifecycle(self):
        serializer = PostSerializer(self.post(), data={'media': None}, partial=True)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        with patch.object(self.storage, 'delete') as delete:
            with self.captureOnCommitCallbacks(execute=True):
                serializer.save()
            delete.assert_called_once_with('quorum/community/old-file')

    def test_post_destroy_cleans_up_media_and_comment_cascades(self):
        post = self.post()
        Content.objects.create(
            author=self.owner, type='comment', title='Comment', parent=post,
            media='quorum/community/comment-file',
        )
        request = APIRequestFactory().delete('/post/')
        with patch.object(self.storage, 'delete') as delete:
            with self.captureOnCommitCallbacks(execute=True) as callbacks:
                response = PostViewSet.as_view({'delete': 'destroy'})(request, pk=post.pk)
                self.assertEqual(response.status_code, 204)
                self.assertFalse(Content.objects.exists())
                delete.assert_not_called()
            self.assertEqual(len(callbacks), 1)
            self.assertEqual(
                {call.args[0] for call in delete.call_args_list},
                {'quorum/community/old-file', 'quorum/community/comment-file'},
            )

    def test_instance_and_queryset_deletes_cover_each_file_model(self):
        for model, field, name in (
            (Profile, 'avatar', 'quorum/accounts/old-image'),
            (Content, 'media', 'quorum/community/old-file'),
            (Resource, 'file', 'resources/old-file'),
        ):
            for bulk in (False, True):
                with self.subTest(model=model.__name__, bulk=bulk):
                    if model is Profile:
                        obj = Profile.objects.get_or_create(
                            user=self.owner, defaults={'profile_type':'staff', 'job_title':'Lecturer', field:name},
                        )[0]
                    elif model is Content:
                        obj = self.post()
                    else:
                        obj = Resource.objects.create(name='Resource', file=name)
                    pk = obj.pk
                    with patch.object(self.storage, 'delete') as delete:
                        with self.captureOnCommitCallbacks(execute=True) as callbacks:
                            result = model.objects.filter(pk=pk).delete() if bulk else obj.delete()
                            self.assertEqual(result[0], 1)
                            self.assertFalse(model.objects.filter(pk=pk).exists())
                            delete.assert_not_called()
                        self.assertEqual(len(callbacks), 1)
                        delete.assert_called_once_with(name)

    def test_user_instance_and_queryset_deletes_capture_owned_files(self):
        for bulk in (False, True):
            with self.subTest(bulk=bulk):
                user = CustomUser.objects.create_user(username=f'deleted-user-{bulk}')
                Profile.objects.create(user=user, avatar='quorum/accounts/cascade-image')
                Content.objects.create(author=user, type='post', title='Post', media='quorum/community/cascade-file')
                with patch.object(self.storage, 'delete') as delete:
                    with self.captureOnCommitCallbacks(execute=True) as callbacks:
                        if bulk:
                            CustomUser.objects.filter(pk=user.pk).delete()
                        else:
                            user.delete()
                        delete.assert_not_called()
                    self.assertEqual(len(callbacks), 1)
                    self.assertEqual(
                        {call.args[0] for call in delete.call_args_list},
                        {'quorum/accounts/cascade-image', 'quorum/community/cascade-file'},
                    )

    def test_delete_rollback_preserves_record_and_file(self):
        post = self.post()
        pk = post.pk
        with patch.object(self.storage, 'delete') as delete:
            with self.captureOnCommitCallbacks(execute=True) as callbacks:
                with self.assertRaises(RuntimeError):
                    with transaction.atomic():
                        post.delete()
                        raise RuntimeError('Roll back')
            self.assertTrue(Content.objects.filter(pk=pk).exists())
            self.assertEqual(callbacks, [])
            delete.assert_not_called()

    def test_shared_reference_survives_replacement_and_cross_feature_delete(self):
        Resource.objects.create(name='Shared', file=self.profile.avatar.name)
        with patch.object(self.storage, 'delete') as delete:
            with self.captureOnCommitCallbacks(execute=True):
                self.profile.avatar = None
                self.profile.save()
            delete.assert_not_called()
            with self.captureOnCommitCallbacks(execute=True):
                Resource.objects.all().delete()
            delete.assert_called_once_with('quorum/accounts/old-image')

    def test_bulk_deletion_deduplicates_shared_names(self):
        first = self.post()
        Content.objects.create(author=self.owner, type='post', title='Second', media=first.media.name)
        with patch.object(self.storage, 'delete') as delete:
            with self.captureOnCommitCallbacks(execute=True) as callbacks:
                Content.objects.all().delete()
            self.assertEqual(len(callbacks), 1)
            delete.assert_called_once_with(first.media.name)

    def test_callback_rechecks_references_added_before_commit(self):
        with patch.object(self.storage, 'delete') as delete:
            with self.captureOnCommitCallbacks(execute=True):
                self.profile.avatar = None
                self.profile.save()
                Resource.objects.create(name='New reference', file='quorum/accounts/old-image')
            delete.assert_not_called()

    def test_invalid_urls_and_traversal_are_not_deleted_or_logged_verbatim(self):
        for name in ('https://example.com/private?signature=secret', '../outside', '/outside'):
            with self.subTest(name=name):
                with patch.object(self.storage, 'delete') as delete:
                    with self.assertLogs('main.media_cleanup', level='ERROR') as logs:
                        with self.captureOnCommitCallbacks(execute=True):
                            schedule_file_cleanup([(self.storage, name)], operation='delete', using='default')
                    delete.assert_not_called()
                    self.assertNotIn(name, logs.output[0])


class MediaCommitTests(MediaFixtures, TransactionTestCase):
    def test_cleanup_failure_is_json_logged_after_real_commit(self):
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(JSONFormatter())
        logger = logging.getLogger('main.media_cleanup')
        logger.addHandler(handler)
        self.addCleanup(logger.removeHandler, handler)
        with patch.object(self.storage, 'delete', side_effect=RuntimeError('secret signed URL')) as delete:
            with transaction.atomic():
                self.profile.avatar = None
                self.profile.save()
                delete.assert_not_called()
        self.profile.refresh_from_db()
        self.assertFalse(self.profile.avatar)
        delete.assert_called_once_with('quorum/accounts/old-image')
        record = json.loads(stream.getvalue())
        self.assertEqual(record['event'], 'media.cleanup_failed')
        self.assertEqual(record['level'], 'ERROR')
        self.assertEqual(record['exception']['type'], 'RuntimeError')
        self.assertIn('operation=clear', record['message'])
        self.assertIn(sha256(b'quorum/accounts/old-image').hexdigest()[:16], record['message'])
        self.assertNotIn('secret signed URL', stream.getvalue())
        self.assertNotIn('old-image', stream.getvalue())

    def test_false_deletion_result_is_logged_without_reversing_commit(self):
        with patch.object(self.storage, 'delete', return_value=False):
            with self.assertLogs('main.media_cleanup', level='ERROR') as logs:
                self.profile.avatar = None
                self.profile.save()
        self.profile.refresh_from_db()
        self.assertFalse(self.profile.avatar)
        self.assertEqual(logs.records[0].event, 'media.cleanup_failed')

    def test_successful_deletion_occurs_after_outer_commit(self):
        with patch.object(self.storage, 'delete') as delete:
            with transaction.atomic():
                self.profile.avatar = None
                self.profile.save()
                delete.assert_not_called()
            delete.assert_called_once_with('quorum/accounts/old-image')
