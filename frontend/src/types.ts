export interface UploadResponse {
  session_id: string;
  filename: string;
  table_count: number;
  row_count: number;
  table_names: string[];
  schema_description: string;
}

export interface ChartConfig {
  type: "bar" | "line" | "pie" | "none";
  data: Record<string, string | number>[];
  x_key: string;
  y_keys: string[];
}

export interface QueryResponse {
  success: boolean;
  error: string | null;
  sql: string;
  answer: string;
  chart: ChartConfig;
  table: {
    columns: string[];
    rows: (string | number | null)[][];
  };
}
