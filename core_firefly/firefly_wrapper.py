#Import seperate background_tasks, allows for processing to be done in background
#and not risk a timeout requesting a page while processing.
from background_task import background
from background_task.models import Task
from background_task.models import CompletedTask

from django.conf import settings

#Import my model and forms
from firefly.models import Job_Submission, Example_Data

#Import firefly
from core_firefly import firefly_class

import numpy as np

import numpy as np
import random
import time
import os
import warnings
from io import BytesIO

from astropy.io import fits
import sys, traceback

time_in_database = 60*60*24
clean_db = True

import sys, os

# Disable
def blockPrint():
    sys.stdout = open(os.devnull, 'w')

# Restore
def enablePrint():
    sys.stdout = sys.__stdout__

def convert_to_fits_table(spectra_list,
						  file_list,
						  output_file):

	#print("Converting", file_list, "to a fits table called", output_file)
	n_spectra = 3

	wavelength    = np.array([])
	original_data = np.array([])
	firefly_model = np.array([])
	flux_error    = np.array([])

	max_length = 0

	#Loop through files, check which one has the largest array
	for file in file_list:
	    
	    hdulist = fits.open(file)

	    if max_length < len(hdulist[1].data['wavelength']):
	        max_length = len(hdulist[1].data['wavelength'])
	    
	    hdulist.close()

	zero_array = np.zeros(max_length)
	#Loop through the files
	for file in file_list:

		print("reading", file)
		hdulist = fits.open(file)

		new_length      = max_length - len(hdulist[1].data['wavelength'])
		temp_wavelength = np.append(hdulist[1].data['wavelength'], np.full(shape = new_length, fill_value = hdulist[1].data['wavelength'][-1]))
		wavelength      = np.append(wavelength, temp_wavelength)

		#Find loglam, pad it out with the last value if its smaller then the largest array so all are same length
		#Append it to the loglam array
		temp_original_data = np.append(hdulist[1].data['original_data'], np.full(shape = new_length, fill_value = hdulist[1].data['original_data'][-1]))
		original_data      = np.append(original_data, temp_original_data)

		#Find ivar, pad it out with the last value if its smaller then the largest array so all are same length
		#Append it to the ivar array
		temp_fierfly_model = np.append(hdulist[1].data['firefly_model'], np.full(shape = new_length, fill_value = hdulist[1].data['firefly_model'][-1]))
		firefly_model      = np.append(firefly_model, temp_fierfly_model)

		temp_flux_error = np.append(hdulist[1].data['flux_error'], np.full(shape = new_length, fill_value = hdulist[1].data['flux_error'][-1]))
		flux_error = np.append(flux_error, temp_flux_error)

		hdulist.close()
		del hdulist

	#Reshape the arrays so they are 2D
	wavelength    = np.reshape(wavelength,    (len(file_list), max_length)) 
	original_data = np.reshape(original_data, (len(file_list), max_length))
	firefly_model = np.reshape(firefly_model, (len(file_list), max_length))
	flux_error    = np.reshape(flux_error,    (len(file_list), max_length))

	#Store the arrays in the correct format
	array_format = str(max_length) + 'D'

	#Create the columns for the fits table
	col0 = fits.Column(name ='spectra',       format = '20A',        array = spectra_list)
	col1 = fits.Column(name ='wavelength',    format = array_format, array = wavelength)
	col2 = fits.Column(name ='original_data', format = array_format, array = original_data)
	col3 = fits.Column(name ='firefly_model', format = array_format, array = firefly_model)
	col4 = fits.Column(name ='flux_error',    format = array_format, array = flux_error)
	
	columns = [col0, col1, col2, col3, col4]

	my_dict = {}
	i = 0

	for file in file_list:
		
		redshift_found = False
		hdul = fits.open(file)
		keys = list(hdul[1].header.keys())

		#print(keys)

		for key in keys:
			if key != 'redshift' and key != 'IMF':
				#print(key)
				pass
			else:
				redshift_found = True
				#print("FOUND")

			if redshift_found:
				if key in my_dict:
					my_dict[key][i] = hdul[1].header[key]
				else:
					thetype = type(hdul[1].header[key])
					if thetype == str:
						my_dict[key] = np.full((len(file_list)), 'N/A', dtype = 'S140')
					else:
						my_dict[key] = np.full((len(file_list)), np.NaN)
					my_dict[key][i] = hdul[1].header[key]

		i = i + 1
		"""
		for key in extra_info_dict:
			extra_info_dict[key] = np.append(extra_info_dict[key], float(hdul[1].header[key]))
		
		for key in extra_info_dict2:
			for i in range(hdul[1].header['ssp_number']):
				extra_info_dict2[key] = np.append(extra_info_dict2[key], float(hdul[1].header[key + str(i)]))
		"""
		hdul.close()
		del hdul

	for key in my_dict:
		myformat = 'D'
		try:
			for i in range(len(file_list)):
				float(my_dict[key][i])
		except:
			myformat = '20A'

		try:
			#print(key, my_dict[key])
			columns.append(fits.Column(name = key, format = myformat, array = my_dict[key]))
		except:
			#print("FAILED:", key)
			pass

	#Add the columns and save the table
	coldefs = fits.ColDefs(columns)

	hdul    = fits.BinTableHDU.from_columns(coldefs)

	hdul.writeto(output_file, overwrite=True)

	for file in file_list:
		os.remove(file)


#Automatically delete job from databse after certain amount of time.
@background(name = 'clean_db', schedule=time_in_database, queue = 'my-queue')
def clean_database(job_id):

	try:
		job_submission = Job_Submission.objects.get(job_id = job_id)
		job_id = job_submission.job_id
		job_submission.delete()
		print("deleted", job_id)
	except:
		print("Failed to delete", job_id)

@background(name = 'firefly', queue = 'my-queue')
def firefly_run(input_file, 
				job_id,
				ageMin,
				ageMax,
				ZMin,
				ZMax,
				flux_units,
				error,
				models_key,
				model_libs,
				imfs,
				wave_medium,
				downgrade_models,
				emissionline_list,
				N_angstrom_masked,
				redshift     = None,
				ra           = None,
				dec          = None,
				vdisp        = None,
				r_instrument = None):

	warnings.filterwarnings("ignore")
	blockPrint()

	#Setup firefly settings
	firefly = firefly_class.Firefly()

	firefly.settings(ageMin           = ageMin,
					 ageMax			  = ageMax,
					 ZMin             = ZMin,
					 ZMax             = ZMax,
					 flux_units       = flux_units,
					 models_key       = models_key,
					 model_libs       = model_libs,
					 imfs             = imfs,
					 data_wave_medium = wave_medium,
					 downgrade_models = downgrade_models)
	
	try:

		output_list = []

		path, file = os.path.split(input_file)

		if os.path.splitext(input_file)[1] == ".fits":
			hdulist      = fits.open(input_file)
			n_spectra    = len(hdulist[1].data["spectra"])
			spectra_list = hdulist[1].data["spectra"]
			hdulist.close()
			del hdulist
		else:
			spectra_list =[os.path.basename(input_file)]
			n_spectra    = 1

		for i in range(n_spectra):
			if os.path.splitext(input_file)[1] == ".ascii":
				
				firefly.model_input(redshift     = redshift,
									ra           = ra,
									dec          = dec,
									vdisp        = vdisp,
									r_instrument = r_instrument)

			output_file_i = os.path.join(settings.TEMP_FILES, "temp" + str(i) + "_" + file)

			enablePrint()
			print(output_file_i, "starting")
			blockPrint()

			#Run firefly to process the data
			output = firefly.run(input_file        = input_file, 
								 output_file       = output_file_i,
								 emissionline_list = emissionline_list,
								 N_angstrom_masked = N_angstrom_masked,
								 n_spectrum        = i)

			enablePrint()
			print(output_file_i, "finished")
			blockPrint()
			output_list.append(output)

		output_file = os.path.join(settings.OUTPUT_FILES, "output_" + file)
		convert_to_fits_table(spectra_list = spectra_list,
							  file_list    = output_list,
							  output_file  = output_file)

		#Get the Job_Submission and save it to the database.
		job_submission = Job_Submission.objects.get(job_id = job_id)
		if os.path.isfile(output_file):
			job_submission.output_file = os.path.relpath(output_file, settings.MEDIA_ROOT)
			job_submission.status = "complete"
		else:
			job_submission.status = "did_not_converge"
		job_submission.save()

		#After completion, remove files from database after certain amount of time
		#so we don't have to store files.
		if clean_db:
			clean_database(job_id)
			
	except:

		traceback.print_exc()

		#Get the Job_Submission and save it to the database.
		job_submission        = Job_Submission.objects.get(job_id = job_id)
		job_submission.status = "failed"
		job_submission.save()

		for file in output_list:
			try:
				os.remove(file)
			except:
				pass

		clean_database(job_id)