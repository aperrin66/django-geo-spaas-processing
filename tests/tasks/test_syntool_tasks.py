"""Tests for Syntool conversion tasks"""
import logging
import subprocess
import unittest
import unittest.mock as mock
from pathlib import Path

import geospaas_processing.tasks
import geospaas_processing.tasks.syntool as tasks_syntool
from geospaas_processing.models import ProcessingResult


class SyntoolTasksTestCase(unittest.TestCase):
    """Tests for syntool tasks"""

    def test_get_db_config(self):
        """Check we get the right database config"""
        with mock.patch('os.environ', {'SYNTOOL_DATABASE_HOST': 'a', 'SYNTOOL_DATABASE_NAME': 'b'}):
            self.assertTupleEqual(tasks_syntool.get_db_config(), ('a', 'b'))

    def test_save_results(self):
        """Check the files resulting from conversion are saved to the
        database
        """
        with mock.patch(
                'geospaas_processing.models.ProcessingResult.objects.get_or_create'
                ) as mock_get_or_create, \
             mock.patch('geospaas.catalog.models.Dataset.objects.get') as mock_get_dataset:
            tasks_syntool.save_results(1, ('foo', 'bar'))
        mock_get_or_create.assert_has_calls((
            mock.call(
                dataset=mock_get_dataset.return_value,
                path='foo',
                type=ProcessingResult.ProcessingResultType.SYNTOOL),
            mock.call(
                dataset=mock_get_dataset.return_value,
                path='bar',
                type=ProcessingResult.ProcessingResultType.SYNTOOL),
        ))

    def test_check_ingested_already_exist(self):
        """If ingested files already exist for the current dataset,
        the current tasks chain should be stopped.
        This does not test the actual chain interruption because it's
        a pain to set up
        """
        mock_queryset = mock.MagicMock()
        mock_queryset.__iter__.return_value = [mock.Mock(path='foo'), mock.Mock(path='bar')]
        with mock.patch('geospaas_processing.models.ProcessingResult.objects.filter',
                        return_value=mock_queryset):
            self.assertTupleEqual(
                tasks_syntool.check_ingested((1,)),
                (1, ['foo', 'bar']))

    def test_check_ingested_dont_exist(self):
        """If no result files exist for the dataset, just pass on the
        arguments
        """
        mock_queryset = mock.MagicMock()
        mock_queryset.exists.return_value = False
        with mock.patch('geospaas_processing.models.ProcessingResult.objects.filter',
                        return_value=mock_queryset):
            self.assertTupleEqual(tasks_syntool.check_ingested((1,)), (1,))

    def test_convert(self):
        """Test that the dataset files are converted to Syntool format
        and the resulting files are saved to the database
        """
        with mock.patch('geospaas_processing.tasks.syntool.SyntoolConversionManager',
                ) as mock_conversion_manager, \
             mock.patch('geospaas_processing.tasks.syntool.save_results') as mock_save_results:
            mock_conversion_manager.return_value.convert.return_value = ('bar', 'baz')
            result = tasks_syntool.convert((1, ('foo',)))
        mock_conversion_manager.assert_called_once_with(geospaas_processing.tasks.WORKING_DIRECTORY)
        mock_conversion_manager.return_value.convert.assert_called_once_with(
            1, 'foo', results_dir=geospaas_processing.tasks.WORKING_DIRECTORY)
        mock_save_results.assert_called_once_with(1, ('bar', 'baz'))
        self.assertTupleEqual(result, (1, ('bar', 'baz')))


class DBInsertTestCase(unittest.TestCase):
    """Tests for the db_insert() task"""

    def setUp(self):
        mock.patch('os.environ',
                   {'SYNTOOL_DATABASE_HOST': 'db', 'SYNTOOL_DATABASE_NAME': 'syntool'}).start()
        self.mock_popen = mock.patch('subprocess.Popen').start()
        self.mock_run = mock.patch('subprocess.run').start()

    def tearDown(self):
        mock.patch.stopall()

    def test_db_insert(self):
        """Test insertion of conversion results into the Syntool
        database
        """
        self.mock_popen.return_value.wait.return_value = 0
        self.mock_run.return_value.returncode = 0
        tasks_syntool.db_insert((1, ('foo',)))

        self.mock_popen.assert_called_with(
            ['syntool-meta2sql', '--chunk_size=100', '-', '--',
             str(Path(geospaas_processing.tasks.WORKING_DIRECTORY, 'foo', 'metadata.json'))],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True)
        self.mock_run.assert_called_with(
            ['mysql', '-h', 'db', 'syntool'],
            stdin=self.mock_popen.return_value.stdout,
            capture_output=True,
            check=True)

    def test_db_insert_subprocess_error(self):
        """Test handling errors when the subprocess is run"""
        self.mock_run.side_effect = subprocess.CalledProcessError(1, '')
        with self.assertRaises(subprocess.CalledProcessError), \
             self.assertLogs(tasks_syntool.logger):
            tasks_syntool.db_insert((1, ('foo',)))

    def test_db_insert_meta2sql_return_code_error(self):
        """Test handling return code != 0 for meta2sql process"""
        self.mock_popen.return_value.wait.return_value = 1
        with self.assertRaises(RuntimeError):
            tasks_syntool.db_insert((1, ('foo',)))

    def test_db_insert_mysql_return_code_error(self):
        """Test handling return code != 0 for mysql process"""
        self.mock_popen.return_value.wait.return_value = 0
        self.mock_run.return_value.returncode = 1
        with self.assertRaises(RuntimeError):
            tasks_syntool.db_insert((1, ('foo',)))


class CleanupIngestedTestCase(unittest.TestCase):
    """Tests for the cleanup_ingested() task"""

    def setUp(self):
        mock.patch('os.environ',
                   {'SYNTOOL_DATABASE_HOST': 'db', 'SYNTOOL_DATABASE_NAME': 'syntool'}).start()
        self.mock_filter = mock.patch(
            'geospaas_processing.tasks.syntool.ProcessingResult.objects.filter').start()
        self.mock_filter.return_value.__iter__.return_value = [
            mock.MagicMock(path='ingested/3413_osi_saf_ice_type_raster/'
                                'ice_type_nh_polstere-100_multi_202302261200')]
        self.mock_rmtree = mock.patch('shutil.rmtree').start()
        self.mock_remove = mock.patch('os.remove').start()
        self.mock_run = mock.patch('subprocess.run').start()

    def tearDown(self):
        mock.patch.stopall()

    def test_cleanup_ingested_created_date(self):
        """Test standard call, deleting based on creation date"""
        with self.assertLogs(tasks_syntool.logger):
            self.assertListEqual(tasks_syntool.cleanup_ingested('2023-01-01', created=False), [
                'ingested/3413_osi_saf_ice_type_raster/'
                'ice_type_nh_polstere-100_multi_202302261200'
            ])
        self.mock_rmtree.assert_called_with(Path(
            geospaas_processing.tasks.WORKING_DIRECTORY,
            'ingested/3413_osi_saf_ice_type_raster/'
            'ice_type_nh_polstere-100_multi_202302261200'))
        self.mock_run.assert_called_with(
            [
                'mysql', '-h', 'db', 'syntool', '-e',
                "DELETE FROM `product_3413_osi_saf_ice_type_raster` WHERE dataset_name = "
                "'ice_type_nh_polstere-100_multi_202302261200';"
            ],
            capture_output=True,
            check=True)
        self.mock_filter.return_value.__iter__.return_value[0].delete.assert_called_once_with()

    def test_cleanup_ingested_dataset_date(self):
        """Test standard call, deleting based on creation date"""
        with self.assertLogs(tasks_syntool.logger):
            self.assertListEqual(tasks_syntool.cleanup_ingested('2023-01-01', created=True), [
                'ingested/3413_osi_saf_ice_type_raster/'
                'ice_type_nh_polstere-100_multi_202302261200'
            ])

    def test_cleanup_ingested_file_result_file(self):
        """Test deleting a file (usually won't happen)"""
        self.mock_rmtree.side_effect = NotADirectoryError
        with self.assertLogs(tasks_syntool.logger):
            self.assertListEqual(tasks_syntool.cleanup_ingested('2023-01-01', created=False), [
                'ingested/3413_osi_saf_ice_type_raster/'
                'ice_type_nh_polstere-100_multi_202302261200'
            ])

    def test_cleanup_ingested_file_not_found(self):
        """Test behavior when the result files are already deleted
        """
        self.mock_rmtree.side_effect = FileNotFoundError
        with self.assertLogs(tasks_syntool.logger, level=logging.WARNING):
            self.assertListEqual(tasks_syntool.cleanup_ingested('2023-01-01', created=False), [
                'ingested/3413_osi_saf_ice_type_raster/'
                'ice_type_nh_polstere-100_multi_202302261200'
            ])

    def test_cleanup_ingested_file_subprocess_error(self):
        """Test behavior when an error occurs running the mysql command
        """
        self.mock_run.side_effect = subprocess.CalledProcessError(1, '')
        with self.assertLogs(tasks_syntool.logger, level=logging.ERROR), \
             self.assertRaises(subprocess.CalledProcessError):
            self.assertListEqual(tasks_syntool.cleanup_ingested('2023-01-01', created=False), [
                'ingested/3413_osi_saf_ice_type_raster/'
                'ice_type_nh_polstere-100_multi_202302261200'
            ])
