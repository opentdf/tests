# minikube

## Using minikube to run the openTDF backend on MacOS
1. Install necessary software:
 - install minikube -  `brew install minikube`
 - install kubectl - `brew install kubectl`
 - install helm - `brew install helm`

2. Execute `./start-minikube`

3. Grab minikube ip by executing `minikube ip`

3. Update `/etc/hosts` file by adding entries to it

   - 192.168.xx.xx    opentdf.local
     
Where `192.168.xx.xx` is your minikube IP

## Viewing Containers Logs in RSYSLOG
1. Execute `kubectl -it exec {RSYSLOG_POD_NAME} bash`
2. Execute `cat my.log`

## Develop

To test the validity of values quickly, use `helm lint` with the `backend/charts`.
Some IDEs require the file to be in the chart directory to lint, copy it over ;)  
