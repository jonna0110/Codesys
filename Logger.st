FUNCTION_BLOCK LoggerRealValues
    VAR
        values : ARRAY [1..cArrSize] OF REAL;
        count : INT := 0;
    END_VAR
    VAR_CONSTANT
        cArrSize : INT := 100;
    END_VAR

    METHOD PUBLIC AddValue
        VAR_INPUT
            value : REAL;
        END_VAR
        BEGIN
            IF THIS^.count < THIS^.cArrSize THEN
                THIS^.count := THIS^.count + 1;
                values[count] := value;

            ELSE
                (*Handle overflow, move array up 1 step and add new value as the newest value *)
                FOR i := 1 TO THIS^.cArrSize - 1 DO
                    THIS^.values[i] := THIS^.values[i + 1];
                END_FOR
            
                values[THIS^.cArrSize] := value;
                THIS^.count := THIS^.cArrSize;
            END_IF

    END_METHOD

    METHOD PUBLIC GetMean
        VAR_OUTPUT
            mean : REAL;
        END_VAR
        VAR
            i : INT;
            sum : REAL := 0.0;
        END_VAR
        BEGIN
            IF THIS^.count = 0 THEN
                mean := 0.0;
                RETURN;
            END_IF
                
            FOR i := 1 TO THIS^.count DO
                sum := sum + THIS^.values[i];
            END_FOR
                
            mean := sum / THIS^.count;

    END_METHOD

    METHOD PUBLIC GetMedian
        VAR_OUTPUT
            median : REAL;
        END_VAR
        VAR
            i : INT;
            j : INT;
            temp : REAL;
            sorted : ARRAY [1..THIS^.cArrSize] OF REAL;
        END_VAR
        BEGIN
            IF THIS^.count = 0 THEN
                median := 0.0;
                RETURN;
            END_IF
            
            (* Copy values to sorted array *)
            FOR i := 1 TO count DO
                sorted[i] := values[i];
            END_FOR
            
            (* Bubble sort *)
            FOR i := 1 TO count - 1 DO
                FOR j := 1 TO count - i DO
                    IF sorted[j] > sorted[j + 1] THEN
                        temp := sorted[j];
                        sorted[j] := sorted[j + 1];
                        sorted[j + 1] := temp;
                    END_IF
                END_FOR
            END_FOR
            
            (* Calculate median *)
            (* Check if the count value is odd (not evenly divisible by 2) *)
            IF THIS^.count MOD 2 = 1 THEN
                median := sorted[(THIS^.count + 1) / 2];
            ELSE
                median := (sorted[THIS^.count / 2] + sorted[THIS^.count / 2 + 1]) / 2.0;
            END_IF
    END_METHOD


    METHOD PUBLIC ClearArray
        THIS^.count := 0;
        FOR i := 1 TO THIS^.cArrSize DO
            values[i] := 0.0;
        END_FOR

    END_METHOD

    METHOD PUBLIC GetValue
    VAR_INPUT
        index : INT;
    END_VAR
    VAR_OUTPUT
        value : REAL;
    END_VAR
        IF index > 0 AND index <= THIS^.count THEN
            value := THIS^.values[index];
        ELSE
            value := 0.0;
        END_IF
    END_METHOD


    PROPERTY PUBLIC GetLowestValue : REAL
        {attribute 'monitoring' := 'call'}
        // The Get accessor reads the value
        PROPERTY GET
            VAR
                i : INT;
                lowest : REAL;
            END_VAR
            BEGIN
                IF THIS^.count = 0 THEN
                    GetLowestValue := 0.0;
                    RETURN;
                END_IF
                
                lowest := THIS^.values[1];
                FOR i := 2 TO THIS^.count DO
                    IF THIS^.values[i] < lowest THEN
                        lowest := THIS^.values[i];
                    END_IF
                END_FOR
                
                GetLowestValue := lowest;
        END_PROPERTY

    PROPERTY PUBLIC GetHighestValue : REAL
        {attribute 'monitoring' := 'call'}
        // The Get accessor reads the value
        PROPERTY GET
            VAR
                i : INT;
                highest : REAL;
            END_VAR
            BEGIN
                IF THIS^.count = 0 THEN
                    GetHighestValue := 0.0;
                    RETURN;
                END_IF
                
                highest := THIS^.values[1];
                FOR i := 2 TO THIS^.count DO
                    IF THIS^.values[i] > highest THEN
                        highest := THIS^.values[i];
                    END_IF
                END_FOR
                
                GetHighestValue := highest;
        END_PROPERTY

    PROPERTY PUBLIC GetCount : INT
        {attribute 'monitoring' := 'call'}
        // The Get accessor reads the value
        PROPERTY GET
            GetCount := THIS^.count;
        END_PROPERTY

END_FUNCTION_BLOCK