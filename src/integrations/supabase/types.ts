export type Json =
  | string
  | number
  | boolean
  | null
  | { [key: string]: Json | undefined }
  | Json[]

export type Database = {
  // Allows to automatically instantiate createClient with right options
  // instead of createClient<Database, { PostgrestVersion: 'XX' }>(URL, KEY)
  __InternalSupabase: {
    PostgrestVersion: "14.5"
  }
  public: {
    Tables: {
      alert_config: {
        Row: {
          active: boolean
          channel: string
          created_at: string
          destination: string | null
          id: string
          threshold: number
          type: string
          updated_at: string
          user_id: string
        }
        Insert: {
          active?: boolean
          channel: string
          created_at?: string
          destination?: string | null
          id?: string
          threshold?: number
          type: string
          updated_at?: string
          user_id: string
        }
        Update: {
          active?: boolean
          channel?: string
          created_at?: string
          destination?: string | null
          id?: string
          threshold?: number
          type?: string
          updated_at?: string
          user_id?: string
        }
        Relationships: []
      }
      alert_history: {
        Row: {
          config_id: string | null
          created_at: string
          id: string
          message: string
          resolved: boolean
          triggered_at: string
          updated_at: string
          user_id: string
        }
        Insert: {
          config_id?: string | null
          created_at?: string
          id?: string
          message?: string
          resolved?: boolean
          triggered_at?: string
          updated_at?: string
          user_id: string
        }
        Update: {
          config_id?: string | null
          created_at?: string
          id?: string
          message?: string
          resolved?: boolean
          triggered_at?: string
          updated_at?: string
          user_id?: string
        }
        Relationships: [
          {
            foreignKeyName: "alert_history_config_id_fkey"
            columns: ["config_id"]
            isOneToOne: false
            referencedRelation: "alert_config"
            referencedColumns: ["id"]
          },
        ]
      }
      backtest_results: {
        Row: {
          created_at: string
          end_date: string
          equity_curve: Json
          id: string
          parameters: Json
          pnl: number
          start_date: string
          strategy: string
          trades: number
          updated_at: string
          user_id: string
          win_rate: number
        }
        Insert: {
          created_at?: string
          end_date: string
          equity_curve?: Json
          id?: string
          parameters?: Json
          pnl?: number
          start_date: string
          strategy: string
          trades?: number
          updated_at?: string
          user_id: string
          win_rate?: number
        }
        Update: {
          created_at?: string
          end_date?: string
          equity_curve?: Json
          id?: string
          parameters?: Json
          pnl?: number
          start_date?: string
          strategy?: string
          trades?: number
          updated_at?: string
          user_id?: string
          win_rate?: number
        }
        Relationships: []
      }
      cooldown_state: {
        Row: {
          cooldown_seconds: number
          created_at: string
          id: string
          last_trade_timestamp: string
          market: string
          updated_at: string
          user_id: string
        }
        Insert: {
          cooldown_seconds?: number
          created_at?: string
          id?: string
          last_trade_timestamp?: string
          market: string
          updated_at?: string
          user_id: string
        }
        Update: {
          cooldown_seconds?: number
          created_at?: string
          id?: string
          last_trade_timestamp?: string
          market?: string
          updated_at?: string
          user_id?: string
        }
        Relationships: []
      }
      copy_trades: {
        Row: {
          created_at: string
          id: string
          market: string
          pnl: number
          price: number | null
          side: string
          size: number
          status: string
          timestamp: string
          updated_at: string
          user_id: string
          wallet: string
        }
        Insert: {
          created_at?: string
          id?: string
          market: string
          pnl?: number
          price?: number | null
          side: string
          size: number
          status?: string
          timestamp?: string
          updated_at?: string
          user_id: string
          wallet: string
        }
        Update: {
          created_at?: string
          id?: string
          market?: string
          pnl?: number
          price?: number | null
          side?: string
          size?: number
          status?: string
          timestamp?: string
          updated_at?: string
          user_id?: string
          wallet?: string
        }
        Relationships: []
      }
      copy_watchlist: {
        Row: {
          active: boolean
          created_at: string
          id: string
          label: string
          updated_at: string
          user_id: string
          wallet_address: string
        }
        Insert: {
          active?: boolean
          created_at?: string
          id?: string
          label?: string
          updated_at?: string
          user_id: string
          wallet_address: string
        }
        Update: {
          active?: boolean
          created_at?: string
          id?: string
          label?: string
          updated_at?: string
          user_id?: string
          wallet_address?: string
        }
        Relationships: []
      }
      historical_candles: {
        Row: {
          asset: string
          bucket_time: string
          close: number
          created_at: string
          high: number
          id: string
          interval: string
          low: number
          open: number
          volume: number
        }
        Insert: {
          asset: string
          bucket_time: string
          close: number
          created_at?: string
          high: number
          id?: string
          interval: string
          low: number
          open: number
          volume?: number
        }
        Update: {
          asset?: string
          bucket_time?: string
          close?: number
          created_at?: string
          high?: number
          id?: string
          interval?: string
          low?: number
          open?: number
          volume?: number
        }
        Relationships: []
      }
      historical_winrate: {
        Row: {
          avg_pnl: number
          created_at: string
          id: string
          losses: number
          strategy: string
          updated_at: string
          user_id: string
          wins: number
        }
        Insert: {
          avg_pnl?: number
          created_at?: string
          id?: string
          losses?: number
          strategy: string
          updated_at?: string
          user_id: string
          wins?: number
        }
        Update: {
          avg_pnl?: number
          created_at?: string
          id?: string
          losses?: number
          strategy?: string
          updated_at?: string
          user_id?: string
          wins?: number
        }
        Relationships: []
      }
      mm_trades: {
        Row: {
          created_at: string
          id: string
          market: string
          pnl: number
          price: number
          side: string
          size: number
          strategy: string | null
          timestamp: string
          updated_at: string
          user_id: string
        }
        Insert: {
          created_at?: string
          id?: string
          market: string
          pnl?: number
          price: number
          side: string
          size: number
          strategy?: string | null
          timestamp?: string
          updated_at?: string
          user_id: string
        }
        Update: {
          created_at?: string
          id?: string
          market?: string
          pnl?: number
          price?: number
          side?: string
          size?: number
          strategy?: string | null
          timestamp?: string
          updated_at?: string
          user_id?: string
        }
        Relationships: []
      }
      strategy_config: {
        Row: {
          created_at: string
          enabled: boolean
          id: string
          name: string
          parameters: Json
          updated_at: string
          user_id: string
        }
        Insert: {
          created_at?: string
          enabled?: boolean
          id?: string
          name: string
          parameters?: Json
          updated_at?: string
          user_id: string
        }
        Update: {
          created_at?: string
          enabled?: boolean
          id?: string
          name?: string
          parameters?: Json
          updated_at?: string
          user_id?: string
        }
        Relationships: []
      }
    }
    Views: {
      [_ in never]: never
    }
    Functions: {
      [_ in never]: never
    }
    Enums: {
      [_ in never]: never
    }
    CompositeTypes: {
      [_ in never]: never
    }
  }
}

type DatabaseWithoutInternals = Omit<Database, "__InternalSupabase">

type DefaultSchema = DatabaseWithoutInternals[Extract<keyof Database, "public">]

export type Tables<
  DefaultSchemaTableNameOrOptions extends
    | keyof (DefaultSchema["Tables"] & DefaultSchema["Views"])
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends (DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof (DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"] &
        DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Views"])
    : never) = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? (DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"] &
      DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Views"])[TableName] extends {
      Row: infer R
    }
    ? R
    : never
  : DefaultSchemaTableNameOrOptions extends keyof (DefaultSchema["Tables"] &
        DefaultSchema["Views"])
    ? (DefaultSchema["Tables"] &
        DefaultSchema["Views"])[DefaultSchemaTableNameOrOptions] extends {
        Row: infer R
      }
      ? R
      : never
    : never

export type TablesInsert<
  DefaultSchemaTableNameOrOptions extends
    | keyof DefaultSchema["Tables"]
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends (DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"]
    : never) = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"][TableName] extends {
      Insert: infer I
    }
    ? I
    : never
  : DefaultSchemaTableNameOrOptions extends keyof DefaultSchema["Tables"]
    ? DefaultSchema["Tables"][DefaultSchemaTableNameOrOptions] extends {
        Insert: infer I
      }
      ? I
      : never
    : never

export type TablesUpdate<
  DefaultSchemaTableNameOrOptions extends
    | keyof DefaultSchema["Tables"]
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends (DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"]
    : never) = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"][TableName] extends {
      Update: infer U
    }
    ? U
    : never
  : DefaultSchemaTableNameOrOptions extends keyof DefaultSchema["Tables"]
    ? DefaultSchema["Tables"][DefaultSchemaTableNameOrOptions] extends {
        Update: infer U
      }
      ? U
      : never
    : never

export type Enums<
  DefaultSchemaEnumNameOrOptions extends
    | keyof DefaultSchema["Enums"]
    | { schema: keyof DatabaseWithoutInternals },
  EnumName extends (DefaultSchemaEnumNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaEnumNameOrOptions["schema"]]["Enums"]
    : never) = never,
> = DefaultSchemaEnumNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[DefaultSchemaEnumNameOrOptions["schema"]]["Enums"][EnumName]
  : DefaultSchemaEnumNameOrOptions extends keyof DefaultSchema["Enums"]
    ? DefaultSchema["Enums"][DefaultSchemaEnumNameOrOptions]
    : never

export type CompositeTypes<
  PublicCompositeTypeNameOrOptions extends
    | keyof DefaultSchema["CompositeTypes"]
    | { schema: keyof DatabaseWithoutInternals },
  CompositeTypeName extends (PublicCompositeTypeNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[PublicCompositeTypeNameOrOptions["schema"]]["CompositeTypes"]
    : never) = never,
> = PublicCompositeTypeNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[PublicCompositeTypeNameOrOptions["schema"]]["CompositeTypes"][CompositeTypeName]
  : PublicCompositeTypeNameOrOptions extends keyof DefaultSchema["CompositeTypes"]
    ? DefaultSchema["CompositeTypes"][PublicCompositeTypeNameOrOptions]
    : never

export const Constants = {
  public: {
    Enums: {},
  },
} as const
