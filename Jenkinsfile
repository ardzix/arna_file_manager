// Production File Manager release; schema and backend configuration gate rollout.
pipeline {
    agent any
    options { skipDefaultCheckout(true); timestamps(); timeout(time: 60, unit: 'MINUTES'); disableConcurrentBuilds(); buildDiscarder(logRotator(numToKeepStr: '20')) }
    parameters {
        booleanParam(name: 'DEPLOY', defaultValue: false, description: 'Migrate, roll and verify the tested main image; leave disabled to validate without deploying')
        booleanParam(name: 'USE_DOCKER_CLOUD', defaultValue: true, description: 'Build with the existing Arnatech Docker Build Cloud endpoint. Failure stops the build; no silent local fallback.')
    }
    environment { DOCKER_CLOUD_BUILDER_ENDPOINT = 'arnatechid/default' }
    stages {
        stage('Checkout approved main') {
            steps {
                deleteDir()
                checkout scm
                sh '''
                    set -eu
                    git diff --exit-code
                    test "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)"
                    git rev-parse HEAD > release-commit.txt
                    python3 deploy/release_id.py > release-id.txt
                    git archive --format=tar -o storage-source.tar HEAD
                    command -v ssh
                    command -v scp
                '''
            }
        }
        stage('Test and publish exact artifact') {
            steps {
                withCredentials([
                    sshUserPrivateKey(credentialsId: 'stag-arnatech-sa-01', keyFileVariable: 'STORAGE_SSH_KEY'),
                    usernamePassword(credentialsId: 'ard-dockerhub', usernameVariable: 'STORAGE_REGISTRY_USER', passwordVariable: 'STORAGE_REGISTRY_TOKEN')
                ]) {
                    sh '''
                        set -eu
                        set +x
                        python3 deploy/registry_credentials.py
                        trap 'rm -rf .release-private' EXIT
                        python3 deploy/cloud_build.py
                        deploy/remote.sh stage
                        deploy/remote.sh build
                    '''
                }
            }
        }
        stage('Validate configuration and migrate') {
            when { expression { params.DEPLOY } }
            steps {
                withCredentials([
                    sshUserPrivateKey(credentialsId: 'stag-arnatech-sa-01', keyFileVariable: 'STORAGE_SSH_KEY'),
                    file(credentialsId: 'file-manager-env', variable: 'STORAGE_ENV_FILE'),
                    file(credentialsId: 'sso_public_pem', variable: 'STORAGE_PUBLIC_KEY')
                ]) {
                    sh 'set -eu; set +x; deploy/remote.sh configuration; deploy/remote.sh migrate'
                }
            }
        }
        stage('Roll and verify production') {
            when { expression { params.DEPLOY } }
            steps {
                withCredentials([sshUserPrivateKey(credentialsId: 'stag-arnatech-sa-01', keyFileVariable: 'STORAGE_SSH_KEY')]) {
                    sh 'set +x; deploy/remote.sh roll'
                }
            }
        }
    }
    post {
        always {
            sh(returnStatus: true, script: 'set +x; rm -rf .release-private')
            withCredentials([sshUserPrivateKey(credentialsId: 'stag-arnatech-sa-01', keyFileVariable: 'STORAGE_SSH_KEY')]) {
                sh(returnStatus: true, script: 'set +x; test ! -s release-id.txt || deploy/remote.sh cleanup')
            }
        }
    }
}
