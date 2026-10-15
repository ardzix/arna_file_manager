// Production File Manager release; schema and backend configuration gate rollout.
pipeline {
    agent any
    options { timestamps(); timeout(time: 60, unit: 'MINUTES'); disableConcurrentBuilds(); buildDiscarder(logRotator(numToKeepStr: '20')) }
    parameters { booleanParam(name: 'DEPLOY', defaultValue: true, description: 'Migrate, roll and verify the tested main image; disable for build-only validation') }
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
                    file(credentialsId: 'file-manager-env', variable: 'STORAGE_ENV_FILE'),
                    file(credentialsId: 'sso_public_pem', variable: 'STORAGE_PUBLIC_KEY'),
                    usernamePassword(credentialsId: 'ard-dockerhub', usernameVariable: 'STORAGE_REGISTRY_USER', passwordVariable: 'STORAGE_REGISTRY_TOKEN')
                ]) {
                    sh '''
                        set -eu
                        set +x
                        python3 deploy/registry_credentials.py
                        trap 'rm -rf .release-private' EXIT
                        deploy/remote.sh stage
                        deploy/remote.sh build
                    '''
                }
            }
        }
        stage('Validate configuration and migrate') {
            when { expression { params.DEPLOY } }
            steps {
                withCredentials([sshUserPrivateKey(credentialsId: 'stag-arnatech-sa-01', keyFileVariable: 'STORAGE_SSH_KEY')]) {
                    sh 'set +x; deploy/remote.sh migrate'
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
            withCredentials([sshUserPrivateKey(credentialsId: 'stag-arnatech-sa-01', keyFileVariable: 'STORAGE_SSH_KEY')]) {
                sh(returnStatus: true, script: 'set +x; test ! -s release-id.txt || deploy/remote.sh cleanup')
            }
        }
    }
}
