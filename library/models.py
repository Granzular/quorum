from django.db import models, router
from django.conf import settings
from uuid6 import uuid7
from main.media_cleanup import FileCleanupQuerySet, delete_with_file_cleanup, save_with_file_cleanup
from main.media_storage import file_storage

class  Resource(models.Model):
    """
    Resources includes Books, videos and audios,etc.
    """
    objects = models.Manager.from_queryset(FileCleanupQuerySet)()

    id = models.UUIDField( primary_key=True, default=uuid7, editable=False, db_index=True)
    name = models.CharField(max_length=128,db_index=True,null=True,blank=True)
    mime_type = models.CharField(max_length=64,null=True,blank=True)
    # reverse relationship of courses
    # reverse relationship of category
    size = models.CharField(max_length=128,null=True,blank=True)
    drive_id = models.CharField(max_length=128,null=True,blank=True)
    preview_url = models.URLField(null=True,blank=True)
    download_url = models.URLField(null=True,blank=True)
    file = models.FileField(
        upload_to=settings.MEDIA_UPLOAD_FOLDERS['library']['resources'],
        storage=file_storage, blank=True, null=True,
    )
    is_active = models.BooleanField(null=True, blank=True)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    def save(self, **kwargs):
        """Preserve Drive indexing while cleaning up changed optional files."""
        return save_with_file_cleanup(self, super().save, **kwargs)

    def delete(self, using=None, keep_parents=False):
        using = using or router.db_for_write(type(self), instance=self)
        return delete_with_file_cleanup(
            self, super().delete, using=using, keep_parents=keep_parents,
        )

    def __str__(self):
        return self.name

    def get_formatted_size(self):
        # process the self.size string into human readable size
        ...
    def get_content_type(self):
        # convert the mime type to user friendly file type
        ...

    class Meta:
        ordering = ['created']

class ResourceCategory(models.Model):
    name = models.CharField(max_length=128)
    books = models.ManyToManyField(Resource, related_name='categories', blank=True)

    def __str__(self):
        return self.name
    
    class Meta:
        verbose_name_plural = 'Resource Categories' 


class Course(models.Model):
    title = models.CharField(max_length=64,null=True,blank=True)
    code = models.CharField(max_length=8)
    level =  models.CharField(max_length=3,null=True,blank=True)
    unit = models.CharField(max_length=2,null=True,blank=True)
    semester = models.CharField(max_length=10,choices=(('first','First semester'),('second','Second Semester')))
    synopsis = models.TextField(null=True,blank=True)
    outline = models.TextField(null=True,blank=True)
    drive_id = models.CharField(max_length=128,null=True, blank=True)
    resource = models.ManyToManyField(Resource,related_name='courses',blank=True)

    def __str__(self):
        return f"{self.code}"
    
    class Meta:
        ordering = ['level']
