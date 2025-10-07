{{/*
Expand the name of the chart.
*/}}
{{- define "mvidarr.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this (by the DNS naming spec).
If release name contains chart name it will be used as a full name.
*/}}
{{- define "mvidarr.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "mvidarr.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "mvidarr.labels" -}}
helm.sh/chart: {{ include "mvidarr.chart" . }}
{{ include "mvidarr.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "mvidarr.selectorLabels" -}}
app.kubernetes.io/name: {{ include "mvidarr.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "mvidarr.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "mvidarr.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
Create the name of the namespace
*/}}
{{- define "mvidarr.namespace" -}}
{{- default .Release.Namespace .Values.namespaceOverride }}
{{- end }}

{{/*
Database connection string
*/}}
{{- define "mvidarr.databaseUrl" -}}
{{- if .Values.database.external.enabled }}
{{- printf "mysql+pymysql://%s:%s@%s:%d/%s" .Values.database.external.username .Values.database.external.password .Values.database.external.host (.Values.database.external.port | int) .Values.database.external.database }}
{{- else }}
{{- printf "mysql+pymysql://%s:%s@%s-mariadb:3306/%s" .Values.database.mariadb.auth.username .Values.database.mariadb.auth.password .Release.Name .Values.database.mariadb.auth.database }}
{{- end }}
{{- end }}

{{/*
Redis connection string
*/}}
{{- define "mvidarr.redisUrl" -}}
{{- if .Values.redis.auth.enabled }}
{{- printf "redis://:%s@%s-redis-master:6379/0" .Values.redis.auth.password .Release.Name }}
{{- else }}
{{- printf "redis://%s-redis-master:6379/0" .Release.Name }}
{{- end }}
{{- end }}

{{/*
Image repository
*/}}
{{- define "mvidarr.image" -}}
{{- $registry := .Values.global.imageRegistry | default .Values.image.registry }}
{{- printf "%s/%s:%s" $registry .Values.image.repository (.Values.image.tag | default .Chart.AppVersion) }}
{{- end }}

{{/*
Storage class
*/}}
{{- define "mvidarr.storageClass" -}}
{{- .Values.global.storageClass | default .Values.storage.media.storageClass }}
{{- end }}

{{/*
Security context for pods
*/}}
{{- define "mvidarr.podSecurityContext" -}}
{{- toYaml .Values.security.podSecurityContext }}
{{- end }}

{{/*
Security context for containers
*/}}
{{- define "mvidarr.containerSecurityContext" -}}
{{- toYaml .Values.security.containerSecurityContext }}
{{- end }}

{{/*
Resource requests and limits
*/}}
{{- define "mvidarr.resources" -}}
{{- toYaml .Values.resources }}
{{- end }}

{{/*
Node selector
*/}}
{{- define "mvidarr.nodeSelector" -}}
{{- toYaml .Values.nodeSelector }}
{{- end }}

{{/*
Tolerations
*/}}
{{- define "mvidarr.tolerations" -}}
{{- toYaml .Values.tolerations }}
{{- end }}

{{/*
Affinity
*/}}
{{- define "mvidarr.affinity" -}}
{{- toYaml .Values.affinity }}
{{- end }}

{{/*
Environment variables
*/}}
{{- define "mvidarr.env" -}}
- name: ENVIRONMENT
  value: {{ .Values.app.environment | quote }}
- name: LOG_LEVEL
  value: {{ .Values.app.logLevel | quote }}
- name: DEBUG
  value: {{ .Values.app.debug | quote }}
- name: DATABASE_URL
  valueFrom:
    secretKeyRef:
      name: {{ include "mvidarr.fullname" . }}-secrets
      key: database-url
- name: REDIS_URL
  valueFrom:
    secretKeyRef:
      name: {{ include "mvidarr.fullname" . }}-secrets
      key: redis-url
- name: SESSION_SECRET_KEY
  valueFrom:
    secretKeyRef:
      name: {{ include "mvidarr.fullname" . }}-secrets
      key: session-secret-key
- name: JWT_SECRET_KEY
  valueFrom:
    secretKeyRef:
      name: {{ include "mvidarr.fullname" . }}-secrets
      key: jwt-secret-key
{{- if .Values.extraEnv }}
{{- toYaml .Values.extraEnv }}
{{- end }}
{{- end }}

{{/*
Volume mounts
*/}}
{{- define "mvidarr.volumeMounts" -}}
- name: media-storage
  mountPath: /app/media
- name: thumbnails-storage
  mountPath: /app/media/thumbnails
- name: temp-storage
  mountPath: /app/temp
- name: config-volume
  mountPath: /app/config
  readOnly: true
- name: logs-volume
  mountPath: /app/logs
{{- if .Values.extraVolumeMounts }}
{{- toYaml .Values.extraVolumeMounts }}
{{- end }}
{{- end }}

{{/*
Volumes
*/}}
{{- define "mvidarr.volumes" -}}
- name: media-storage
  persistentVolumeClaim:
    claimName: {{ include "mvidarr.fullname" . }}-media-pvc
- name: thumbnails-storage
  persistentVolumeClaim:
    claimName: {{ include "mvidarr.fullname" . }}-thumbnails-pvc
- name: temp-storage
  persistentVolumeClaim:
    claimName: {{ include "mvidarr.fullname" . }}-temp-pvc
- name: config-volume
  configMap:
    name: {{ include "mvidarr.fullname" . }}-config
- name: logs-volume
  emptyDir:
    sizeLimit: 1Gi
{{- if .Values.extraVolumes }}
{{- toYaml .Values.extraVolumes }}
{{- end }}
{{- end }}