"""
abstracted classes, more like interfaces
"""


class SaverConfig(object):
        pass


class SaverLogger(object):

    def log_save(self, **kwargs):
        pass

    def log_delete(self, **kwargs):
        pass


class SaverManagerFactory(object):

    def manager(self):
        pass

    def simple_access(self):
        pass


class _SaverCoreManager(object):

    def files_delete(self, files_saved, dry_run=False, ):
        """
        workhorse for deletion

        `files_saved`
            `dict`
            format =
                files_saved[size] = (target_filename, bucket_name)
        """
        pass


class SaverManager(_SaverCoreManager):

    def generate_filenames(self, resizerResultset, guid, selected_resizes=None, archive_original=None):
        pass

    def files_save(self, resizerResultset, guid, selected_resizes=None, archive_original=None, dry_run=False, ):
        pass

    # _SaverCoreManager.files_delete


class SaverSimpleAccess(_SaverCoreManager):

    def file_save(self, bucket_name, filename, wrappedFile, upload_type="public", dry_run=False, ):
        pass

    def simple_saves_mapping(self, bucket_name, filename):
        pass

    # _SaverCoreManager.files_delete
