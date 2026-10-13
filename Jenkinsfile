pipeline {
    agent any

    options {
        timestamps()
        timeout(time: 45, unit: 'MINUTES')
        disableConcurrentBuilds()
    }

    environment {
        // Publishing only until the coordinated schema/configuration release.
        // Do not enable the legacy rollout without a bounded migration gate.
        DEPLOY = 'false'

        // Docker
        DOCKER_IMAGE = 'ardzix/file_manager'
        DOCKER_TAG = "${BUILD_NUMBER}"
        DOCKER_REGISTRY_CREDENTIALS = 'ard-dockerhub'

        // Swarm
        STACK_NAME = 'file_manager'
        REPLICAS = '1'
        NETWORK_NAME = 'production'
        SERVICE_PORT = '8000'

        // VPS
        VPS_HOST = '172.105.124.43'
    }

    stages {

        stage('Clean Workspace') {
            steps {
                deleteDir()
            }
        }

        stage('Checkout Code') {
            steps {
                checkout scm
            }
        }

        stage('Inject Env & PEM') {
            steps {
                withCredentials([
                    file(credentialsId: 'file-manager-env', variable: 'ENV_FILE'),
                    file(credentialsId: 'sso_public_pem', variable: 'PUBLIC_PEM_FILE')
                ]) {
                    sh '''
                        set -eu
                        set +x
                        cp "$ENV_FILE" .env
                        cp "$PUBLIC_PEM_FILE" public.pem
                    '''
                }
            }
        }

        stage('Build Docker Image') {
            steps {
                script {
                    docker.build("${DOCKER_IMAGE}:${DOCKER_TAG}", ".")
                }
            }
        }

        stage('Test isolated file and device contracts') {
            options { timeout(time: 5, unit: 'MINUTES') }
            steps {
                sh '''
                    set -eu
                    docker run --rm --network none "$DOCKER_IMAGE:$DOCKER_TAG" python scripts/test_device_access.py
                '''
            }
        }

        stage('Push Docker Image') {
            steps {
                script {
                    docker.withRegistry('https://index.docker.io/v1/', DOCKER_REGISTRY_CREDENTIALS) {
                        docker.image("${DOCKER_IMAGE}:${DOCKER_TAG}").push()
                        docker.image("${DOCKER_IMAGE}:${DOCKER_TAG}").push('latest')
                    }
                }
            }
        }

        stage('Deploy to Swarm') {
            when {
                expression { return env.DEPLOY?.toBoolean() ?: false }
            }
            steps {
                withCredentials([
                    sshUserPrivateKey(
                        credentialsId: 'stag-arnatech-sa-01',
                        keyFileVariable: 'SSH_KEY_FILE'
                    )
                ]) {
                    sh """
                        echo "[INFO] Preparing VPS deployment..."
                        ssh -i "$SSH_KEY_FILE" -o StrictHostKeyChecking=no root@${VPS_HOST} "mkdir -p /root/${STACK_NAME}"

                        echo "[INFO] Copying env..."
                        scp -i "$SSH_KEY_FILE" -o StrictHostKeyChecking=no .env root@${VPS_HOST}:/root/${STACK_NAME}/.env

                        echo "[INFO] Deploying Docker service..."
                        ssh -i "$SSH_KEY_FILE" -o StrictHostKeyChecking=no root@${VPS_HOST} <<EOF
docker swarm init || true
docker network create --driver overlay ${NETWORK_NAME} || true
docker service rm ${STACK_NAME} || true

docker service create \
  --name ${STACK_NAME} \
  --replicas ${REPLICAS} \
  --network ${NETWORK_NAME} \
  --env-file /root/${STACK_NAME}/.env \
  --publish ${SERVICE_PORT}:8000 \
  ${DOCKER_IMAGE}:${DOCKER_TAG}

echo "[INFO] Deploy success."
EOF
                    """
                }
            }
        }
    }

    post {
        always {
            echo 'Pipeline finished!'
        }
        success {
            echo 'Tested image published; production rollout is gated separately.'
        }
        failure {
            echo 'Pipeline failed.'
        }
    }
}
