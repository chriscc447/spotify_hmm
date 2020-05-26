import pickle
import numpy as np

def load_all(model_path = 'data/rf_model.sav', scaler_path = 'data/scalers.data'):
    with open(model_path, 'rb') as f:
        model = pickle.load(f)

    with open(scaler_path, 'rb') as f:
        scaler = pickle.load(f)
        centers = scaler['center']
        factors = scaler['scale']
    return model, centers, factors

clf, centers, factors = load_all()

def predict(data):
    scaled = (np.array(data) - centers)/factors
    x = scaled.reshape(1,-1)
    return clf.predict(x)[0]