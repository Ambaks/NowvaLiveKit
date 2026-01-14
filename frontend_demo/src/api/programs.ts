const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export interface ProgramGenerationRequest {
  user_id: string;
  name: string;
  email: string;
  height_cm: number;
  weight_kg: number;
  goal_category: string;
  goal_raw: string;
  duration_weeks: number;
  days_per_week: number;
  fitness_level: string;
  age: number;
  sex: string;
  session_duration: number;
  injury_history: string;
  specific_sport: string;
  has_vbt_capability: boolean;
  user_notes: string;
}

export interface ProgramGenerationResponse {
  job_id: string;
  status: string;
  message: string;
}

export interface JobStatusResponse {
  job_id: string;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  progress: number;
  current_week?: number;
  total_weeks?: number;
  error_message?: string;
  program_id?: string;
}

export const programsApi = {
  async generateProgram(data: ProgramGenerationRequest): Promise<ProgramGenerationResponse> {
    const response = await fetch(`${API_BASE_URL}/api/programs/generate`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(data),
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Failed to generate program');
    }

    return response.json();
  },

  async getJobStatus(jobId: string): Promise<JobStatusResponse> {
    const response = await fetch(`${API_BASE_URL}/api/programs/status/${jobId}`);

    if (!response.ok) {
      throw new Error('Failed to fetch job status');
    }

    return response.json();
  },

  async getProgramPdf(programId: string): Promise<Blob> {
    const response = await fetch(`${API_BASE_URL}/api/programs/${programId}/pdf`);

    if (!response.ok) {
      throw new Error('Failed to fetch PDF');
    }

    return response.blob();
  },
};

// Generate a simple UUID for user_id
export const generateUserId = (): string => {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === 'x' ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
};
