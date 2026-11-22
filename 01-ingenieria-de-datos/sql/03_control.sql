-- Tabla de control: una fila por tabla procesada en cada corrida

CREATE TABLE secop_control.control_corridas (
  id_corrida string COMMENT 'Identificador de la ejecución, por ejemplo plata-20261101-060512',
  job string COMMENT 'Nombre del job de Glue que escribió la fila',
  tabla string COMMENT 'Tabla de plata procesada, por ejemplo secop_silver.procesos',
  inicio timestamp COMMENT 'Inicio del procesamiento de la tabla',
  fin timestamp COMMENT 'Fin del procesamiento de la tabla',
  estado string COMMENT 'exito o fallo',
  filas_leidas bigint COMMENT 'Filas leídas de bronce en esta corrida',
  filas_validas bigint COMMENT 'Filas escritas en la tabla de válidos',
  filas_rechazadas bigint COMMENT 'Filas escritas en la tabla de rechazados',
  rechazos_por_motivo map<string, bigint> COMMENT 'Conteo de rechazos por motivo',
  cuadre_ok boolean COMMENT 'true si filas_leidas = filas_validas + filas_rechazadas',
  ultima_fecha_ingesta date COMMENT 'Última partición fecha= de bronce incluida en la corrida',
  snapshot_id bigint COMMENT 'Snapshot de Iceberg de la tabla después de escribir',
  mensaje_error string COMMENT 'Detalle del error si estado = fallo')
LOCATION 's3://proyecto-integrador-bucket-01/control/control_corridas'
TBLPROPERTIES (
  'table_type'='iceberg',
  'write_compression'='snappy',
  'format'='parquet'
);
