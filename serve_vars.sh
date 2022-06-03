SERVICE_IP=$(kubectl get svc -l app=womm-server-$1 -o jsonpath --template '{ .items[0].spec.clusterIP }')
