import axios from "axios";
import type { UploadResponse, QueryResponse } from "../types";

const BASE = "http://localhost:8090/api";

export const api = {
  upload: async (file: File): Promise<UploadResponse> => {
    const form = new FormData();
    form.append("file", file);
    const { data } = await axios.post<UploadResponse>(`${BASE}/upload`, form);
    return data;
  },

  query: async (session_id: string, question: string): Promise<QueryResponse> => {
    const { data } = await axios.post<QueryResponse>(`${BASE}/query`, {
      session_id,
      question,
    });
    return data;
  },
};
