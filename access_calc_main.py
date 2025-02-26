# Accessibility Calculator for ArcGIS Pro v2.1
# Christopher D. Higgins
# Department of Human Geography
# University of Toronto Scarborough
# https://higgicd.github.io
# tool help can be found at https://github.com/higgicd/Accessibility_Toolbox

import os, sys
import math
import datetime
import time
import arcpy
import multiprocessing
from arcpy import env
env.overwriteOutput = True
arcpy.CheckOutExtension("Network")

# ----- this tool can be run from the command line -----
# open Start Menu > ArcGIS > Python Command Prompt
# run this: C:\Progra~1\ArcGIS\Pro\bin\Python\scripts\propy.bat D:\access_calc_main.py
# change file path of the access_calc_main.py in the code above^

# ----- parameters ----- # change all these as you see fit
# --- origins ---
#origins_i_input = r"D:/access_multi/Toronto_Accessibility_GIS.gdb/Toronto_1k" # file path for origins
#i_id_field = "OID" # origins id field name
#search_tolerance_i = "5000 Meters" # network location search tolerance
#search_criteria_i = [["Streets", "SHAPE"]] # location search criteria
#search_query_i = None # location search criteria

# --- destinations ---
#destinations_j_input = r"D:/access_multi/Toronto_Accessibility_GIS.gdb/Toronto_10k"
#j_id_field = "OID" # destinations id field name
#o_j_field = "weight" # destinations opportunities field name
#search_tolerance_j = "5000 Meters" # network location search tolerance
#search_criteria_j = [["Streets", "SHAPE"]] # location search criteria
#search_query_j = None # location search criteria

# --- network analysis ---
#input_network = r"D:/access_multi/Toronto_Accessibility_GIS.gdb/GTFS/TransitNetwork_ND" # file path to network dataset
#travel_mode = "Public transit time" # travel mode
#cutoff = None # travel time cut-off
#time_of_day = datetime.datetime.strptime("12/30/2019 8:00:00 AM", '%m/%d/%Y %I:%M:%S %p') # change start datetime for your analysis
#time_of_day = None # or use None
#selected_impedance_function = ["HN1997", "CUMR45", "MGAUS180"] # see online or parameters file for list

#batch_size_factor = 500 # this controls how many origins are in a single batch
#output_dir = r"D:/access_multi" # directory for output and worker files
#output_gdb = "Access_multi_100" # output geodatabase name
#del_i_eq_j = "true" # delete lines where i = j? "true" or "false"
#join_back_i = "true" # join output back to origins? "true" or "false"

# ----- main -----

def workspace_setup(output_dir, output_gdb):
    # setup output gdb workspace
    if arcpy.Exists(os.path.join(output_dir+"/"+output_gdb+".gdb")):
        arcpy.management.Delete(os.path.join(output_dir+"/"+output_gdb+".gdb"))
        arcpy.management.CreateFileGDB(output_dir, output_gdb+".gdb")
    else:
        arcpy.management.CreateFileGDB(output_dir, output_gdb+".gdb")
    
    workspace = os.path.join(output_dir+"/"+output_gdb+".gdb")
    return workspace

def scratchWorkspace_setup(output_dir, output_gdb):
    # setup output worker folders
    if arcpy.Exists(os.path.join(output_dir+"/"+output_gdb+"_workers")):
        arcpy.management.Delete(os.path.join(output_dir+"/"+output_gdb+"_workers"))
        arcpy.management.CreateFolder(output_dir, output_gdb+"_workers")
    else:
        arcpy.management.CreateFolder(output_dir, output_gdb+"_workers")
    
    scratchWorkspace = os.path.join(output_dir+"/"+output_gdb+"_workers")
    return scratchWorkspace

def field_type_x(input_fc, field_name):
    field = arcpy.ListFields(input_fc, field_name)[0]
    if field.type == "Double":
        field_type = "DOUBLE"
    if field.type == "Integer":
        field_type = "LONG"
    if field.type == "Single":
        field_type = "FLOAT"
    if field.type == "SmallInteger":
        field_type = "SHORT"
    if field.type == "String":
        field_type = "TEXT"
    if field.type == "OID":
        field_type = "LONG"
    return field_type

def turbo_joiner(target_fc, target_id_field, join_fc, join_id_field, join_value_field):
    # setup join dictionary
    join_fields_list = [join_id_field, join_value_field]
    valueDict = {r[0]:r[1] for r in arcpy.da.SearchCursor(join_fc, join_fields_list)}

    # setup target info
    join_value_field_type = field_type_x(join_fc, join_value_field)
    arcpy.management.AddField(target_fc, join_value_field, join_value_field_type)
    target_fields_list = [target_id_field, join_value_field]
    
    with arcpy.da.UpdateCursor(target_fc, target_fields_list) as updateRows:
        for updateRow in updateRows:
            keyValue = updateRow[0]
            if keyValue in valueDict:
                updateRow[1] = valueDict.get(keyValue)
                updateRows.updateRow(updateRow)

def field_map_x(input_fc, field_name, output_field_name):
    field_map_x = arcpy.FieldMap() # create the field map object
    field_map_x.addInputField(input_fc, field_name) # add the input field name to the map
    field_x_output = field_map_x.outputField # create the outputfield object
    field_x_output.name = output_field_name # give the output field a name
    field_map_x.outputField = field_x_output # copy named output field back
    return field_map_x

def list_unique(input_fc, field):
    unique_list = []
    with arcpy.da.SearchCursor(input_fc, field) as cursor:
        for row in cursor:
            if row[0] not in unique_list:
                unique_list.append(row[0])
    return unique_list
    
def cpu_count(cpu_tot):
    if cpu_tot == 1:
        cpu_num = 1
    else:
        cpu_num = cpu_tot - 1
    return cpu_num

def batch_size_f(input_fc, batch_size_factor):
    cpu_num = cpu_count(multiprocessing.cpu_count())
    arcpy.AddMessage("There are "+str(multiprocessing.cpu_count())+" cpu cores on this machine, using "+str(cpu_num))
    origins_i_count = int(arcpy.management.GetCount(input_fc).getOutput(0))
    
    if int(math.ceil(origins_i_count/cpu_num)) <= batch_size_factor:
        batch_size = int(math.ceil(origins_i_count/cpu_num)+1)
        batch_count = int(math.ceil(origins_i_count/batch_size))
        arcpy.AddMessage("Batching is optimized with "+str(batch_count)+" chunks of origins")
    else:
        batch_size = batch_size_factor
        batch_count = int(math.ceil(origins_i_count/batch_size_factor))
        arcpy.AddMessage("Batching "+str(batch_count)+" chunks of origins")
    return batch_size

def batch_i_setup(input_fc, batch_size):
    arcpy.management.Sort(input_fc, os.path.join(arcpy.env.workspace+"/origins_i"), "Shape ASCENDING", "PEANO")
    # no advanced licence? comment out the Sort above and substitute in the line below
    #arcpy.conversion.FeatureClassToFeatureClass(input_fc, arcpy.env.workspace, "origins_i")
    arcpy.management.AddField(os.path.join(arcpy.env.workspace+"/origins_i"), "batch_id", "LONG")
    arcpy.management.CalculateField(os.path.join(arcpy.env.workspace+"/origins_i"), "batch_id",
                                    "math.ceil(autoIncrement()/"+str(batch_size)+")", "PYTHON3",
                                    "rec=0\ndef autoIncrement():\n    global rec\n    pStart    = 1 \n    pInterval = 1 \n " +
                                    "   if (rec == 0): \n        rec = pStart \n    else: \n        rec += pInterval \n  " +
                                    "  return rec")
    batch_fc = os.path.join(arcpy.env.workspace+"/origins_i")
    return batch_fc

def calculate_nax_locations(input_fc, input_type, input_network, search_tolerance, search_criteria, search_query, travel_mode):
    arcpy.AddMessage("Calculating "+input_type+" Network Locations...")
    print("Calculating "+input_type+" Network Locations...")
    arcpy.nax.CalculateLocations(input_fc, input_network, 
                                 search_tolerance = search_tolerance, 
                                 search_criteria = search_criteria, 
                                 search_query = search_query,
                                 travel_mode = travel_mode,
                                 exclude_restricted_elements = "EXCLUDE")

def create_dict(input_fc, key_field, value_field):
    valueDict = {r[0]:r[1] for r in arcpy.da.SearchCursor(input_fc, [key_field, value_field])}
    return valueDict

def preprocess_x(input_fc, input_type, id_field, o_j_field, input_network, search_tolerance, search_criteria, search_query, travel_mode, batch_size):
    
    # add field mappings
    if input_type == "origins_i":
        field_mappings = arcpy.FieldMappings()
        field_mappings.addFieldMap(field_map_x(input_fc, id_field, "i_id"))
    
    if input_type == "destinations_j":
        field_mappings = arcpy.FieldMappings()
        field_mappings.addFieldMap(field_map_x(input_fc, id_field, "j_id"))
        field_mappings.addFieldMap(field_map_x(input_fc, o_j_field, "o_j"))
        
    # convert to points if required
    describe_x = arcpy.Describe(input_fc, input_type)
    if describe_x.ShapeType !="Point":
        arcpy.AddMessage("Converting "+input_type+" to points...")
        arcpy.management.FeatureToPoint(input_fc, r"in_memory/"+input_type+"_point", "INSIDE")
        arcpy.conversion.FeatureClassToFeatureClass(r"in_memory/"+input_type+"_point", r"in_memory", 
                                                    input_type, field_mapping = field_mappings)
    else:
        arcpy.AddMessage(input_type+" is already points...")
        arcpy.conversion.FeatureClassToFeatureClass(input_fc, r"in_memory", 
                                                    input_type, field_mapping = field_mappings)
    
    # prepare origins/destinations output
    if input_type == "origins_i":
        arcpy.management.AddField(r"in_memory/"+input_type, "i_id_text", "TEXT", field_length = 255)
        arcpy.management.CalculateField(r"in_memory/"+input_type, "i_id_text", "!i_id!", "PYTHON3")
        output_fc = batch_i_setup(r"in_memory/"+input_type, batch_size)
    else:
        arcpy.management.AddField(r"in_memory/"+input_type, "j_id_text", "TEXT", field_length = 255)
        arcpy.management.CalculateField(r"in_memory/"+input_type, "j_id_text", "!j_id!", "PYTHON3")
        
        layer = arcpy.management.MakeFeatureLayer(r"in_memory/"+input_type, input_type+"_view")
        arcpy.management.SelectLayerByAttribute(layer, "NEW_SELECTION", "o_j > 0")
        
        arcpy.conversion.FeatureClassToFeatureClass(layer, arcpy.env.workspace, input_type)
        output_fc = os.path.join(arcpy.env.workspace+"/"+input_type)
    
    # calculate network locations
    calculate_nax_locations(output_fc, input_type, input_network, search_tolerance, search_criteria, search_query, travel_mode)
    arcpy.AddMessage("Finished pre-processing "+input_type)
    arcpy.management.Delete(r"in_memory")
    return output_fc

def access_multi(jobs):
    from importlib import reload
    import parameters
    reload(parameters)
    from parameters import impedance_f
    
    batch_id = jobs[0]
    scratchworkspace = jobs[1]
    origins_i = jobs[2]
    destinations_j = jobs[3]
    input_network = jobs[4]
    travel_mode = jobs[5]
    cutoff = jobs[6]
    time_of_day = jobs[7]
    selected_impedance_function = jobs[8]
    o_j_dict = jobs[9]
    del_i_eq_j = jobs[10]
    
    arcpy.management.CreateFileGDB(scratchworkspace, "batch_"+str(batch_id)+".gdb")
    worker_gdb = os.path.join(scratchworkspace+"/batch_"+str(batch_id)+".gdb")
        
    network_layer = "network_layer"+str(batch_id)
    arcpy.nax.MakeNetworkDatasetLayer(input_network, network_layer)
    odcm = arcpy.nax.OriginDestinationCostMatrix(network_layer)
        
    # nax layer properties
    odcm.travelMode = travel_mode
    odcm.timeUnits = arcpy.nax.TimeUnits.Minutes
    odcm.defaultImpedanceCutoff = cutoff
    odcm.lineShapeType = arcpy.nax.LineShapeType.NoLine
    if time_of_day != None:
        odcm.timeOfDay = time_of_day
    else:
        odcm.timeOfDay = None
    
    # 1 DESTINATIONS
    # map j_id field
    candidate_fields_j = arcpy.ListFields(destinations_j)
    field_mappings_j = odcm.fieldMappings(arcpy.nax.OriginDestinationCostMatrixInputDataType.Destinations,
                                              True, candidate_fields_j)
    field_mappings_j["Name"].mappedFieldName = "j_id"
    
    # load destinations
    odcm.load(arcpy.nax.OriginDestinationCostMatrixInputDataType.Destinations, 
              features = destinations_j, 
              field_mappings = field_mappings_j,
              append = False)
    
    # 2 ORIGINS
    # map i_id field
    temp_origins_i = arcpy.management.MakeFeatureLayer(origins_i, "origins_i"+str(batch_id), '"batch_id" = ' + str(batch_id))
    arcpy.conversion.FeatureClassToFeatureClass(temp_origins_i, "in_memory", "origins"+str(batch_id))
    
    origins_i = r"in_memory/origins"+str(batch_id)
    
    candidate_fields_i = arcpy.ListFields(origins_i)
    field_mappings_i = odcm.fieldMappings(arcpy.nax.OriginDestinationCostMatrixInputDataType.Origins, 
                                          True, candidate_fields_i)
    field_mappings_i["Name"].mappedFieldName = "i_id"
    
    # load origins
    odcm.load(arcpy.nax.OriginDestinationCostMatrixInputDataType.Origins,
              features = origins_i, 
              field_mappings = field_mappings_i, 
              append = False)
    
    # 3 SOLVE
    arcpy.AddMessage("Solving OD Matrix...")
    result = odcm.solve()

    # 4 EXPORT results to a feature class
    # fail? skip
    if not result.solveSucceeded:
        return

    result.export(arcpy.nax.OriginDestinationCostMatrixOutputDataType.Lines,
                  os.path.join(r"in_memory", "od_lines_"+str(batch_id)))
    od_lines = os.path.join(r"in_memory", "od_lines_"+str(batch_id))
        
    # ----- un-comment this and comment-out the above if you want to store the od_lines on disk -----
    #result.export(arcpy.nax.OriginDestinationCostMatrixOutputDataType.Lines, 
    #              os.path.join(worker_gdb+"\\od_lines_"+str(batch_id)))
    #od_lines = os.path.join(worker_gdb+"\\od_lines_"+str(batch_id))
    
    # 5 ASSIGN key variable names - might be a localization issue here
    t_ij = 'Total_Time'
    i_id_text = 'OriginName'
    j_id_text = 'DestinationName'
    
    # 6 DELETE rows where i == j:
    if del_i_eq_j == "true":
        arcpy.management.MakeFeatureLayer(od_lines, "od_lines_view")
        arcpy.management.SelectLayerByAttribute("od_lines_view", "NEW_SELECTION", "OriginName <> DestinationName")
        arcpy.management.SelectLayerByAttribute("od_lines_view", "SWITCH_SELECTION")
        if int(arcpy.management.GetCount("od_lines_view").getOutput(0)) > 0:
            arcpy.management.DeleteRows("od_lines_view")
        else:
            arcpy.AddMessage("Can't delete where i = j: inputs don't match")
    
    # 7 CALCULATE ACCESSIBILITY
    for f in selected_impedance_function:
        f_name = f
        arcpy.management.AddField(od_lines, "Ai_"+f_name, "DOUBLE")
        access_fields = [j_id_text, t_ij, "Ai_"+f_name]
        with arcpy.da.UpdateCursor(od_lines, access_fields) as updateRows:
            for updateRow in updateRows:
                updateRow[2] = o_j_dict.get(updateRow[0])*parameters.impedance_f(updateRow[1], f_name)
                updateRows.updateRow(updateRow)
    
    # 8 CALCULATE SUMMARY STATISTICS
    arcpy.AddMessage("Summarizing accessibility...")
    sum_fields = ["Ai_"+f_field+" SUM" for f_field in selected_impedance_function]
    sum_fields_str = ";".join(sum_fields)
    arcpy.analysis.Statistics(od_lines, os.path.join(worker_gdb+"\\output_batch_"+str(batch_id)), sum_fields_str, "OriginName")
    output_table = os.path.join(worker_gdb+"\\output_batch_"+str(batch_id))
    arcpy.management.Delete(r"in_memory")
    return output_table

# ----- execute -----

def main(input_network, travel_mode, cutoff,
         time_of_day, selected_impedance_function,
         origins_i_input, i_id_field, 
         search_tolerance_i, search_criteria_i, search_query_i,
         destinations_j_input, j_id_field, o_j_field,
         search_tolerance_j, search_criteria_j, search_query_j,
         batch_size_factor,
         output_dir, output_gdb,
         del_i_eq_j, join_back_i):
    
    # --- check opportunities_j field type compatibility ---
    o_j_field_type = field_type_x(destinations_j_input, o_j_field)
    if o_j_field_type == "TEXT":
        raise Exception(str(o_j_field)+" field type is text")
    
    # --- setup workspace ---
    arcpy.env.workspace = workspace_setup(output_dir, output_gdb)
    arcpy.env.scratchWorkspace = scratchWorkspace_setup(output_dir, output_gdb)
    
    # --- setup batching ---
    batch_size = batch_size_f(origins_i_input, batch_size_factor)
    
    # --- pre-process origins ---
    origins_i = preprocess_x(input_fc = origins_i_input,
                             input_type = "origins_i", 
                             id_field = i_id_field,
                             o_j_field = None,
                             input_network = input_network, 
                             search_tolerance = search_tolerance_i, 
                             search_criteria = search_criteria_i,
                             search_query = search_query_i,
                             travel_mode = travel_mode,
                             batch_size = batch_size)
    #print(origins_i)
    origins_i_dict = create_dict(origins_i, key_field = "i_id_text", value_field = "i_id")
    
    # ----- destinations -----
    destinations_j = preprocess_x(input_fc = destinations_j_input,
                                  input_type = "destinations_j",
                                  id_field = j_id_field,
                                  o_j_field = o_j_field,
                                  input_network = input_network,
                                  search_tolerance = search_tolerance_j,
                                  search_criteria = search_criteria_j,
                                  search_query = search_query_j,
                                  travel_mode = travel_mode,
                                  batch_size = None)
    #print(destinations_j)
    o_j_dict = create_dict(destinations_j, key_field = "j_id_text", value_field = "o_j")
    
    # worker iterator
    batch_list = list_unique(os.path.join(arcpy.env.workspace+"/origins_i"), "batch_id")
    
    jobs = []
    # adds tuples of the parameters that need to be given to the worker function to the jobs list
    for batch_id in batch_list:
        jobs.append((batch_id, arcpy.env.scratchWorkspace, 
                     origins_i, destinations_j, 
                     input_network, travel_mode, 
                     cutoff, time_of_day,
                     selected_impedance_function, 
                     o_j_dict, del_i_eq_j))
    
    # multiprocessing
    multiprocessing.set_executable(os.path.join(sys.exec_prefix, 'pythonw.exe'))
    arcpy.AddMessage("Sending batch to multiprocessing pool...")
    pool = multiprocessing.Pool(processes = cpu_count(multiprocessing.cpu_count()))
    #result = pool.map(access_multi, jobs)
    result = [x for x in pool.map(access_multi, jobs) if x is not None]
    pool.close()
    pool.join()
    arcpy.AddMessage("Multiprocessing complete, merging results...")
    access_output = arcpy.management.Merge(result, arcpy.env.workspace+"/output_"+output_gdb)
    
    # add back original i_id
    turbo_joiner(target_fc = access_output, 
                 target_id_field = 'OriginName', 
                 join_fc = origins_i, 
                 join_id_field = 'i_id_text', 
                 join_value_field = 'i_id')
    
    if join_back_i == "true":
        # join accessibility output back to origins input
        join_fields = ["SUM_Ai_"+f_field for f_field in selected_impedance_function]
        join_fields.insert(0, "FREQUENCY")
        arcpy.AddMessage("Joining accessibility output to origins_i...")
        arcpy.management.JoinField(origins_i_input, i_id_field, access_output, "i_id", join_fields)
    
    # ----- clean up: this deletes the workers directory. comment-out if you want to keep -----
    arcpy.management.Delete(arcpy.env.scratchWorkspace)

if __name__ == '__main__':
    start_time = time.time()
    main(input_network, travel_mode, cutoff,
         time_of_day, selected_impedance_function,
         origins_i_input, i_id_field, 
         search_tolerance_i, search_criteria_i, search_query_i,
         destinations_j_input, j_id_field, o_j_field,
         search_tolerance_j, search_criteria_j, search_query_j,
         batch_size_factor, output_dir, output_gdb, del_i_eq_j, join_back_i)
    elapsed_time = time.time() - start_time
    arcpy.AddMessage("ODCM calculation took "+str(elapsed_time/60)+" minutes...")
