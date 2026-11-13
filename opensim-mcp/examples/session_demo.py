"""Example trusted API script; load a model before running this file."""
print("OpenSim API script executed")
result = {"model_name": model.getName(), "coordinates": model.getNumCoordinates(),
          "opensim_version": osim.GetVersionAndDate()}
