/**
 * Authentication utilities and state management
 */

import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { apiClient } from './api';
import type { User } from './types';

interface AuthState {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;

  login: (email: string, password: string) => Promise<void>;
  register: (
    email: string,
    password: string,
    firstName?: string,
    lastName?: string,
  ) => Promise<void>;
  logout: () => Promise<void>;
  fetchUser: () => Promise<void>;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user: null,
      isAuthenticated: false,
      isLoading: false,

      login: async (email: string, password: string) => {
        set({ isLoading: true });
        try {
          const response = await apiClient.post('/accounts/login/', {
            email,
            password,
          });
          const user = response.data.user;
          set({ user, isAuthenticated: true, isLoading: false });
        } catch (error) {
          set({ isLoading: false });
          throw error;
        }
      },

      register: async (
        email: string,
        password: string,
        firstName?: string,
        lastName?: string,
      ) => {
        set({ isLoading: true });
        try {
          const response = await apiClient.post('/accounts/registration/', {
            email,
            password1: password,
            password2: password,
            firstName,
            lastName,
          });
          const user = response.data.user;
          set({ user, isAuthenticated: true, isLoading: false });
        } catch (error) {
          set({ isLoading: false });
          throw error;
        }
      },

      logout: async () => {
        try {
          await apiClient.post('/accounts/logout/');
        } catch (error) {
          console.error('Logout error:', error);
        }
        set({ user: null, isAuthenticated: false });
      },

      fetchUser: async () => {
        set({ isLoading: true });
        try {
          const response = await apiClient.get('/accounts/user/');
          const user = response.data;
          set({ user, isAuthenticated: true, isLoading: false });
        } catch {
          set({ user: null, isAuthenticated: false, isLoading: false });
        }
      },
    }),
    {
      name: 'auth-storage',
      partialize: (state) => ({
        user: state.user,
        isAuthenticated: state.isAuthenticated,
      }),
    },
  ),
);
