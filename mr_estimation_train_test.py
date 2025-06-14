# Stellar mass and radius estimation

from numpy import mean
from sklearn import preprocessing
from sklearn.linear_model import LinearRegression
from sklearn.linear_model import BayesianRidge
from sklearn.ensemble import RandomForestRegressor
from sklearn.neighbors import KNeighborsRegressor
from sklearn.tree import DecisionTreeRegressor
from sklearn.svm import SVR
from sklearn.neural_network import MLPRegressor
from sklearn.ensemble import StackingRegressor
from sklearn.model_selection import train_test_split
from sklearn.model_selection import GridSearchCV  # To perform the search for the best parameters
from sklearn.metrics import mean_absolute_error  # define the metric to use for the evaluation
from matplotlib import pyplot
from joblib import dump, load
import pandas as pd
import numpy as np
import os

# this method creates necessary directories to store the model and results
def setup_directories():
    directories = ['experiments', 'results']
    
    for directory in directories:
        if not os.path.exists(directory):
            os.makedirs(directory)
            print(f"Created directory: {directory}")
        else:
            print(f"Directory already exists: {directory}")

# this script imports the data with the information of the stars
def get_dataset():
    data = pd.read_table('data/data_sample_mass_radius.txt', sep="\t")
    # read data with errors
    df = data[
        ['R', 'eR1', 'eR2', 'M', 'eM1', 'eM2', 'Teff', 'eTeff1', 'eTeff2', 'logg', 'elogg1', 'elogg2', 'Meta', 'eMeta1',
         'eMeta2', 'L',
         'eL1', 'eL2']]

    # clean NA values (simply remove the corresponding columns)
    df.dropna(inplace=True, axis=0)
    return df


# augment data using uncertainties
def data_augmentation_with_uncertainties(X_input, y_input, n_samples):
    # Generate samples for every input point using a uniform distribution

    # Input data comes in the form: X_input ( feat0, efeat0_1, efeat0_2, feat1, efeat1_1, efeat1_2, ...)
    # that is, every feature is followed by two error bounds (lower and upper)

    # Separate data and errors

    # Input data used for the experiments, example
    # X_input['Teff', 'eTeff1', 'eTeff2', 'logg', 'elogg1', 'elogg2', 'Meta', 'eMeta1', 'eMeta2', 'L', 'eL1', 'eL2']]
    # y_input['M, 'eM1', 'eM2'] or y['R, 'eR1', 'eR2']

    # read features

    X = X_input[:, 0::3]

    # read errors
    m, n = X_input.shape
    num_features = int(n / 3)
    Xe = np.empty((m, num_features * 2), float)
    jj = 0
    kk = 0
    for ii in range(num_features):
        Xe[:, kk] = X_input[:, 1 + jj]
        kk += 1
        Xe[:, kk] = X_input[:, 2 + jj]
        kk += 1
        jj = jj + 3

    # repeat for the target variable
    y = y_input[:, 0::3]
    ye = y_input[:, 1::]

    if n_samples == 0:  # no random sampling is needed, return original data without error bounds
        return X, np.ravel(y)

    # Initialize random number generator
    from numpy.random import default_rng

    seed = 1
    rng = default_rng(seed)

    first = True
    jj = 0
    # iterate over the arrays
    for (s_x, s_xe, s_y, s_ye) in zip(X, Xe, y, ye):
        # generate new samples
        y_new = rng.uniform(s_y - s_ye[0], s_y + s_ye[1], (n_samples, 1))

        X_new = np.empty((n_samples, num_features), float)
        ee = 0
        for ff in range(num_features):
            new_sample = rng.uniform(s_x[ff] - s_xe[ee + 0], s_x[ff] + s_xe[ee + 1], (1, n_samples))
            X_new[:, ff] = new_sample
            ee = ee + 2

        
        if first:  # to initialize aug variables
            y_aug = np.vstack((y[0, :], y_new))
            X_aug = np.vstack((X[0, :], X_new))
            first = False
        else:
            y_aug = np.vstack((y_aug, y[jj, :], y_new))
            X_aug = np.vstack((X_aug, X[jj, :], X_new))
        jj += 1

    return X_aug, np.ravel(y_aug)


# get a stacking ensemble of models using the best selection
def get_best_stacking(target):
    # define the level 0 models
    # the best combination is as follows
    level0 = list()

    if target == 'M':
        # for M
        level0.append(('nnet',
                        MLPRegressor(activation='relu', hidden_layer_sizes=(25, 25, 25, 25), learning_rate='adaptive',
                                    learning_rate_init=0.2, max_iter=1000, solver='sgd', alpha=0.01,
                                    random_state=0, verbose=False)))
        level0.append(('rf', RandomForestRegressor(random_state=0)))
        level0.append(('knn', KNeighborsRegressor()))
        # SVR
        tuned_parameters_svm = [{'kernel': ['rbf'], 'gamma': [1e-3, 1e-4],
                                 'C': [1, 10, 100, 1000]}]
        clf_svm = GridSearchCV(SVR(), tuned_parameters_svm, scoring='neg_mean_absolute_error')
        level0.append(('svr', clf_svm))
    elif target == 'R':
        # for R
        level0.append(('nnet',
                       MLPRegressor(activation='relu', hidden_layer_sizes=(25, 25, 25, 25), learning_rate='adaptive',
                                    learning_rate_init=0.09, max_iter=1000, solver='sgd', alpha=0.01,
                                    random_state=0, verbose=False)))

        # SVR
        tuned_parameters_svm = [{'kernel': ['rbf'], 'gamma': [1e-3, 1e-4],
                             'C': [1, 10, 100, 1000]}]
        clf_svm = GridSearchCV(SVR(), tuned_parameters_svm, scoring='neg_mean_absolute_error')
        level0.append(('svr', clf_svm))

    # define meta learner model
    level1 = BayesianRidge()

    # define the stacking ensemble
    stacking_model = StackingRegressor(estimators=level0, final_estimator=level1, cv = 2)
    return stacking_model


# get a list of models to evaluate
def get_models(target):
    models = dict()

    # LinearRegression
    models['lr'] = LinearRegression()

    # DecisionTree
    # parameter to optimize in the decision tree
    tuned_parameters_dtr = [{'min_samples_leaf': [5, 10, 50, 100]}]
    clf_dtr = GridSearchCV(DecisionTreeRegressor(), tuned_parameters_dtr, scoring='neg_mean_absolute_error')
    models['dtr'] = clf_dtr

    # RandomForest
    models['rf'] = RandomForestRegressor()

    # SVR
    tuned_parameters_svm = [{'kernel': ['rbf'], 'gamma': [1e-3, 1e-4],
                             'C': [1, 10, 100, 1000]}]
    clf_svm = GridSearchCV(SVR(), tuned_parameters_svm, scoring='neg_mean_absolute_error')
    models['svm'] = clf_svm

    models['bayes'] = BayesianRidge()
    models['knn'] = KNeighborsRegressor()

    if target == 'M':
        # Neural Network (for the M)
        models['nnet'] = MLPRegressor(activation='relu', hidden_layer_sizes=(25, 25, 25, 25), learning_rate='adaptive',
                                     learning_rate_init=0.2, max_iter=1000, solver='sgd', alpha=0.01, random_state=0,
                                     verbose=True)
    elif target == 'R':
        # Neural Network (for the R)
        models['nnet'] = MLPRegressor(activation='relu', hidden_layer_sizes=(25, 25, 25, 25), learning_rate='adaptive',
                                  learning_rate_init=0.09, max_iter=1000, solver='sgd', alpha=0.01, random_state=0,
                                  verbose=True)

    models['stacking'] = get_best_stacking(target)

    return models


# evaluate a given model using a train/test split
def evaluate_model(model, X_train, y_train, X_test, y_test):
    model.fit(X_train, y_train)  # perform training
    y_pred = model.predict(X_test)
    score = mean_absolute_error(y_test, y_pred)
    return score, y_pred


##############################
# Mass and radius estimation #
##############################

# Setup directories
setup_directories()

# Read raw data
data = get_dataset()

# Chose the target variable to estimate (mass 'M' or radius 'R')
target = 'M'
# target = 'R'


# to read target with errors eM1/eM2 or eR1/eR2
y_ser = data.loc[:, [target, 'e' + target + '1', 'e' + target + '2']]
y = y_ser.to_numpy()

# # Selection of the data to be used for the regression (read also the errors)
X_ser = data.loc[:,
        ['Teff', 'eTeff1', 'eTeff2', 'logg', 'elogg1', 'elogg2', 'Meta', 'eMeta1', 'eMeta2', 'L', 'eL1', 'eL2']]
# X_ser = data.loc[:,
#           ['Teff', 'eTeff1', 'eTeff2', 'L', 'eL1', 'eL2']]
# X_ser = data.loc[:,
#         ['Teff', 'eTeff1', 'eTeff2', 'Meta', 'eMeta1', 'eMeta2', 'L', 'eL1', 'eL2']]


X = X_ser.to_numpy()

# perform train test split (train 80%, test 20%)
X_train_prev, X_test_prev, y_train_prev, y_test_prev = train_test_split(X, y, test_size=0.2, random_state=1)

# Data augmentation: generate samples within the interval defined by the errors

# define number of samples to include
n_samples = 10
X_train, y_train = data_augmentation_with_uncertainties(X_train_prev, y_train_prev, n_samples)
n_samples = 0 # sometimes we need more samples for the test
X_test, y_test = data_augmentation_with_uncertainties(X_test_prev, y_test_prev, n_samples)

# Normalize data
scaler = preprocessing.StandardScaler().fit(X_train)
X_train_norm = scaler.transform(X_train)
X_test_norm = scaler.transform(X_test)

# get the models to evaluate
models = get_models(target)

# evaluate the models and store results
results, names, predictions = list(), list(), list()
for name, model in models.items():
    scores, y_pred = evaluate_model(model, X_train_norm, y_train, X_test_norm, y_test)
    results.append(scores)
    predictions.append(y_pred)
    names.append(name)
    print('>%s %.3f' % (name, mean(scores)))

# save model (and test data) for further analysis?
dump(models, 'experiments/models_' + target + '.joblib')
dump([X_test_norm, y_test, n_samples], 'experiments/test_data_' + target + '.joblib')

# debug
# save results/data in txt format to compare with other models
#np.savetxt('experiments/exp2_test_data_' + target + '.txt', X_test_prev, delimiter=',')  # X_test data NOT normalized
#np.savetxt('experiments/exp2_test_y_' + target + '.txt', y_test_prev, delimiter=',')  # y_test

# prediction for stacking (7), but we can save all the predictions
# np.savetxt('experiments/predictions_' + target + '.txt', predictions[7], delimiter=',')  # prediction for stacking (7)

# plot comparison of different models
pyplot.bar(names, results)
pyplot.show()
